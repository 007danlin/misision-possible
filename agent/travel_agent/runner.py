import asyncio
import json
import time
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from .domain import AgentTurn, ChangePreview, Intent, State, Telemetry, apply_intent
from .model import ModelError, PROMPT_VERSION, QwenModel, Settings, canonical_intent
from .tools import ToolError, ToolRegistry, allowed
from .destinations import DestinationUnavailable, resolve_destination, destination_question


def missing_questions(spec):
    questions = []
    if not spec.origin:
        questions.append("Из какого города отправляетесь?")
    if not spec.dates:
        questions.append("Какие точные даты поездки?")
    if spec.dates and spec.duration_days is not None:
        calendar_days = (spec.dates.end - spec.dates.start).days + 1
        if spec.duration_days != calendar_days:
            questions.append(
                f"По датам получается {calendar_days} календарных дней, а указано {spec.duration_days}. Уточните длительность в днях или даты поездки."
            )
    if not spec.travellers.adults:
        questions.append("Сколько взрослых поедет?")
    if any(age is None for age in spec.travellers.children):
        questions.append("Сколько лет каждому ребёнку?")
    if spec.budget is None:
        questions.append("Какой бюджет в рублях и что в него должно входить?")
    elif not spec.budget_scope:
        questions.append(
            "Бюджет на всю поездку, только бронируемые услуги или только отель?"
        )
    elif spec.budget_scope == "whole_trip" and spec.expense_reserve is None:
        questions.append(
            "Сколько из общего бюджета оставить на питание и другие расходы вне бронирования?"
        )
    return questions


async def run_turn(
    state: State,
    message: str,
    tools: ToolRegistry,
    model=None,
    timeout=None,
    progress=None,
) -> AgentTurn:
    """Return a proposal; never mutate state, persist data, select or book a plan."""
    progress = progress or (lambda **event: None)
    progress(stage="understanding")
    start = time.monotonic()
    settings = model.settings if model else Settings.from_env()
    model = model or QwenModel(settings)
    budget = min(settings.timeout, timeout if timeout is not None else settings.timeout)
    metrics = Telemetry(
        model=settings.model, provider=settings.provider, prompt_version=PROMPT_VERSION
    )
    base = dict(
        based_on_revision=state.revision,
        trip_spec=state.trip_spec.model_copy(deep=True),
        data_mode=tools.data_mode,
        telemetry=metrics,
    )

    def result(status, text, **kwargs):
        metrics.total_ms = round((time.monotonic() - start) * 1000)
        if status != "error" and metrics.first_useful_ms is None:
            metrics.first_useful_ms = metrics.total_ms
        if status != "error" and "selection" not in kwargs:
            kwargs["selection"] = state.selection
        return AgentTurn(**(base | kwargs), status=status, assistant_message=text)

    async def call(name, *args):
        if len(metrics.tool_calls) >= 2:
            raise ToolError("Достигнут предел двух вызовов инструментов.")
        metrics.tool_calls.append(name)
        return await getattr(tools, name)(*args)

    if not message.strip() or len(message) > 12000:
        return result(
            "error",
            "Сообщение пустое или слишком длинное.",
            error_code="invalid_message",
        )
    from .origin_followup import needs_initial_origin

    if needs_initial_origin(state, message):
        question = "Из какого города отправляетесь?"
        return result(
            "needs_input", question, questions=[question],
            selection=dict(state.selection, pending_origin_request=message),
        )
    retry_directions = False
    pending_direction = state.selection.get("pending_direction_request")
    if (isinstance(pending_direction, str) and pending_direction
            and not state.trip_spec.destination
            and message.strip().casefold().rstrip(".!?") in {
                "повтори подбор", "повторить подбор", "попробуй ещё раз", "попробуй еще раз", "повтори",
            }):
        message = pending_direction
        retry_directions = True
        state = state.model_copy(deep=True)
        state.selection.pop("pending_direction_request", None)
    elif pending_direction:
        # A new request supersedes the retry marker; successful later choices
        # must not resurrect an older request when the user says "repeat".
        state = state.model_copy(deep=True)
        state.selection.pop("pending_direction_request", None)
    pending = state.selection.get("pending_origin_request")
    if isinstance(pending, str) and pending:
        # Parse the original wishes together with the reply, so an early
        # clarification cannot silently discard budget, dates or preferences.
        message = pending + "\nОтвет на вопрос «Из какого города отправляетесь?»: " + message
        state = state.model_copy(deep=True)
        state.selection.pop("pending_origin_request", None)
        # Retry must retain the original request if inference fails.
        base["selection"] = dict(state.selection, pending_origin_request=pending)

    if state.search_mode == "hotels":
        from .conversation_reply import conversation_reply

        reply = conversation_reply(message)
        if reply:
            questions = list(state.questions)
            if not questions and not state.hotel_options and "?" in state.assistant_message:
                questions = [state.assistant_message]
            return result(
                "needs_input" if questions or not state.hotel_options else "choosing",
                reply + (" " + questions[0] if questions else ""),
                questions=questions,
                hotel_options=state.hotel_options,
                search_url=state.search_url,
                selection=state.selection,
                destination_options=state.selection.get("direction_options", []),
            )
    try:
        async with asyncio.timeout(budget):
            if (
                state.search_mode == "hotels"
                and state.hotel_options
                and re.fullmatch(
                    r"\s*(?:что (?:пишут|говорят)(?: в отзывах)?|покажи отзывы|отзывы)(?: (?:о|про) (?:шум|тишину|чистоту|питание|первый|второй|третий))?[?.!]*\s*",
                    message,
                    re.I,
                )
            ):
                from .journey import review_answer

                index = (
                    1
                    if "второй" in message.lower()
                    else 2
                    if "третий" in message.lower()
                    else 0
                )
                return result(
                    "choosing",
                    review_answer(
                        state.hotel_options[min(index, len(state.hotel_options) - 1)],
                        message,
                    ),
                    hotel_options=state.hotel_options,
                    search_url=state.search_url,
                    selection=state.selection,
                )
            context = {
                "today": datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat(),
                "trip_spec": state.trip_spec.model_dump(
                    mode="json", exclude_defaults=state.search_mode == "hotels"
                ),
                "selected_plan_id": state.selected_plan.id
                if state.selected_plan
                else None,
                "history": state.history[-5:],
                "message": message,
                "search_mode": state.search_mode,
                "last_assistant_message": state.assistant_message,
                "last_questions": state.questions,
                "displayed_directions": state.selection.get("direction_options", []),
                "displayed_hotels": [
                    {
                        "position": i + 1,
                        "name": h.get("name"),
                        "reasons": h.get("reasons", []),
                    }
                    for i, h in enumerate(state.hotel_options)
                ],
            }
            from .fast_intent import (
                fast_intent,
                protect_child_count,
                protect_added_children,
                protect_stay_length,
                protect_duration_units,
                protect_adult_count,
                protect_explicit_forest,
                protect_hotel_budget_scope,
                protect_explicit_polarity,
                protect_hotel_question,
                protect_journey_language,
            )

            from .calendar_followup import calendar_followup

            from .origin_followup import origin_followup
            from .money_followup import money_followup

            from .inspiration import direction_choice

            direct = Intent(action="inspire") if retry_directions else (
                direction_choice(state, message) if state.search_mode == "hotels" else None
            )
            direct = direct or origin_followup(state, message) or money_followup(state, message) or calendar_followup(message)
            direct = direct or (
                fast_intent(state, message)
                if state.search_mode == "hotels" and isinstance(model, QwenModel)
                else None
            )
            repair = None
            for attempt in range(2):
                if direct is not None:
                    raw, usage = direct.model_dump_json(exclude_unset=True), {}
                else:
                    metrics.model_calls += 1
                    model_start = time.monotonic()
                    try:
                        raw, usage = await model.extract(
                            context,
                            repair,
                            max(0.01, budget - (time.monotonic() - start)),
                        )
                    finally:
                        metrics.model_ms += round(
                            (time.monotonic() - model_start) * 1000
                        )
                for key, value in usage.items():
                    metrics.usage[key] = metrics.usage.get(key, 0) + value
                try:
                    intent = Intent.model_validate_json(
                        canonical_intent(
                            raw, message if state.search_mode == "hotels" else None
                        )
                    )
                    intent = protect_child_count(intent, message, state.trip_spec)
                    if state.search_mode == "hotels":
                        intent = protect_added_children(
                            intent, message, state.trip_spec
                        )
                        intent = protect_stay_length(intent, message, state.trip_spec)
                        intent = protect_duration_units(intent, message)
                        intent = protect_adult_count(intent, message)
                        intent = protect_explicit_forest(intent, message)
                        intent = protect_hotel_budget_scope(intent, message)
                        intent = protect_journey_language(
                            protect_hotel_question(
                                protect_explicit_polarity(intent, message), message
                            ),
                            message,
                        )
                    from .grounding import ground_intent

                    intent = ground_intent(intent, message, state.trip_spec)
                    spec = apply_intent(state.trip_spec, intent, message)
                    if state.search_mode == "hotels":
                        if (
                            spec.destination != state.trip_spec.destination
                            or intent.action == "restore_options"
                        ):
                            spec.excluded_hotel_ids = []
                        if intent.action == "replace_options" and spec.destination == state.trip_spec.destination:
                            if spec.keep_hotel:
                                return result(
                                    "needs_input",
                                    "Выбранный отель закреплён. Снять закрепление и заменить подборку?",
                                    questions=["Можно заменить закреплённый отель?"],
                                )
                            spec.excluded_hotel_ids = list(
                                dict.fromkeys(
                                    spec.excluded_hotel_ids
                                    + [h["id"] for h in state.hotel_options]
                                )
                            )[-100:]
                        if spec.keep_hotel and state.selected_hotel:
                            spec.locked_hotel_id = state.selected_hotel["id"]
                        elif not spec.keep_hotel:
                            spec.locked_hotel_id = None
                    if intent.add_locks and (
                        not state.selected_plan
                        or not set(intent.add_locks)
                        <= set(state.selected_plan.component_ids)
                    ):
                        raise ValueError(
                            "only existing selected component IDs may be locked"
                        )
                    break
                except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                    # Do not send raw model output, secrets or traces to logs.
                    direct = None
                    repair = {
                        "validation_error": str(exc)[:1200],
                        "previous_output": raw[:10000],
                    }
                    if attempt == 1:
                        raise ModelError("model_invalid_json") from exc
            patch = {
                k: v
                for k, v in spec.model_dump(mode="json").items()
                if v != state.trip_spec.model_dump(mode="json")[k]
            }
            updates = dict(trip_spec=spec, patch=patch)
            progress(stage="understood", trip_spec=spec.model_dump(mode="json"))
            if (
                state.search_mode != "hotels"
                and spec.country
                and spec.country.casefold() not in {"россия", "russia", "ru", "рф"}
            ):
                return result(
                    "needs_input",
                    "Сейчас подбираем поездки по России. Направление не заменял.",
                    questions=["Рассмотреть поездку по России?"],
                    **updates,
                )
            if state.search_mode == "hotels":
                base["data_mode"] = "public_catalogue_demo_rates"
                from .hotel_selection import (
                    missing_hotel_questions,
                    select_hotels,
                    response_text,
                    explain_hotels,
                )
                from .ostrovok import search_hotels
                from . import journey

                if intent.questions:
                    return result(
                        "needs_input",
                        intent.questions[0],
                        questions=intent.questions,
                        **updates,
                    )
                if (
                    intent.action == "explain"
                    and spec.keep_hotel
                    and set(patch)
                    <= {
                        "keep_hotel",
                        "locked_hotel_id",
                        "trip_budget",
                        "include_transport",
                    }
                    and state.hotel_options
                    and re.search(r"дорог|добрать", message, re.I)
                ):
                    h = state.selected_hotel
                    if not h:
                        return result(
                            "choosing",
                            "Откройте нужный отель и выберите способ добраться в его карточке.",
                            hotel_options=state.hotel_options,
                            **updates,
                        )
                    return result(
                        "choosing",
                        "Отель оставил. Сравните дорогу и выберите подходящий вариант.",
                        hotel_options=state.hotel_options,
                        selection=dict(
                            state.selection, open_panel="transport", hotel_id=h["id"]
                        ),
                        **updates,
                    )
                if intent.action == "nearby" and state.hotel_options and not patch:
                    from .places import nearby_places

                    index = min(
                        (intent.hotel_reference or 1) - 1, len(state.hotel_options) - 1
                    )
                    hotels = list(state.hotel_options)
                    h = dict(hotels[index])
                    h["nearby_places"] = nearby_places(h, spec)
                    hotels[index] = h
                    return result(
                        "choosing",
                        "Открыл места рядом с отелем. Расстояния на схеме — по прямой, а не время в пути.",
                        hotel_options=hotels,
                        selection=dict(
                            state.selection, open_panel="nearby", hotel_id=h["id"]
                        ),
                        **updates,
                    )
                if intent.action == "reviews" and state.hotel_options and not patch:
                    index = (intent.hotel_reference or 1) - 1
                    return result(
                        "choosing",
                        journey.review_answer(
                            state.hotel_options[
                                min(index, len(state.hotel_options) - 1)
                            ],
                            message,
                        ),
                        hotel_options=state.hotel_options,
                        search_url=state.search_url,
                        selection=state.selection,
                        **updates,
                    )
                if intent.action == "explain" and not patch and state.hotel_options:
                    return result(
                        "choosing",
                        explain_hotels(state.hotel_options, intent.hotel_reference, message),
                        hotel_options=state.hotel_options,
                        search_url=state.search_url,
                        selection=state.selection,
                        **updates,
                    )
                from .inspiration import direction_options, inspiration_text, resolve_directions, direction_context, QUESTIONS

                if not spec.destination:
                    if not spec.origin:
                        question = QUESTIONS["origin"]
                        return result(
                            "needs_input", question, questions=[question],
                            selection=state.selection, **updates,
                        )
                    candidates = direction_options(spec)
                    if not candidates:
                        return result("needs_input", QUESTIONS["coverage"], questions=[QUESTIONS["coverage"]], **updates)
                    from .inspiration import simple_direction_choices

                    simple = simple_direction_choices(spec, message, state.history, candidates)
                    if simple is not None:
                        directions, question = resolve_directions(simple, candidates, message=message, spec=spec, history=state.history)
                        return result(
                            "needs_input", question or inspiration_text(spec, directions),
                            questions=[question] if question else [],
                            destination_options=directions,
                            selection=dict(state.selection, direction_options=directions),
                            **updates,
                        )
                    progress(stage="matching_directions", trip_spec=spec.model_dump(mode="json"))
                    metrics.model_calls += 1
                    model_start = time.monotonic()
                    try:
                        # Leave time to return the already validated spec before
                        # the turn deadline. Timeout must not erase an origin or
                        # wishes successfully understood earlier in this turn.
                        remaining = max(0.01, budget - (time.monotonic() - start) - 1)
                        async with asyncio.timeout(remaining):
                            raw, usage = await model.extract(direction_context(
                                spec, message, state.history,
                                state.selection.get("direction_options", []), candidates,
                            ), None, remaining)
                        directions, question = resolve_directions(raw, candidates, message=message, spec=spec, history=state.history[-5:])
                    except (ModelError, TimeoutError):
                        question = "Пожелания сохранил, но подбор направлений не завершился. Напишите «Повтори подбор» или уточните пожелания."
                        return result(
                            "needs_input", question, questions=[question],
                            selection=dict(state.selection, pending_direction_request=message),
                            **updates,
                        )
                    finally:
                        metrics.model_ms += round((time.monotonic() - model_start) * 1000)
                    for key, value in usage.items():
                        metrics.usage[key] = metrics.usage.get(key, 0) + value
                    # A valid single answer is not proof that no alternatives fit.
                    # Give the model one bounded chance to compare the remaining
                    # catalogue under exactly the same wishes. Never pad with IDs
                    # chosen by code, and retain the valid first answer on failure.
                    remaining_candidates = [
                        d for d in candidates
                        if d["id"] not in {item["id"] for item in directions}
                    ]
                    # Additional ideas must not silently expand a domestic
                    # shortlist abroad when no other country was requested.
                    selected_countries = {
                        d["country"] for d in candidates
                        if d["id"] in {item["id"] for item in directions}
                    }
                    if not spec.country and selected_countries == {"Россия"}:
                        remaining_candidates = [d for d in remaining_candidates if d["country"] == "Россия"]
                    remaining = budget - (time.monotonic() - start) - 1
                    from .inspiration import proximity_requested

                    short_travel = proximity_requested(" ".join([message, *state.history, *spec.preferences]))
                    broad_request = json.loads(raw).get("scope") == "broad"
                    if (broad_request and not short_travel and len(directions) == 1
                            and not question and remaining_candidates and remaining > 1):
                        alternative_context = direction_context(
                            spec, message, state.history,
                            [*state.selection.get("direction_options", []), *directions],
                            remaining_candidates,
                        )
                        alternative_context["alternative_search"] = True
                        metrics.model_calls += 1
                        model_start = time.monotonic()
                        try:
                            async with asyncio.timeout(remaining):
                                alternative_raw, alternative_usage = await model.extract(
                                    alternative_context, None, remaining,
                                )
                            for key, value in alternative_usage.items():
                                metrics.usage[key] = metrics.usage.get(key, 0) + value
                            alternatives, alternative_question = resolve_directions(
                                alternative_raw, remaining_candidates,
                                message=message, spec=spec, history=state.history[-5:],
                            )
                            if alternatives and not alternative_question:
                                directions = [*directions, *alternatives[:2]]
                        except (ModelError, TimeoutError):
                            pass
                        finally:
                            metrics.model_ms += round((time.monotonic() - model_start) * 1000)
                    return result(
                        "needs_input", question or inspiration_text(spec, directions),
                        questions=[question] if question else [],
                        destination_options=directions,
                        selection=dict(state.selection, direction_options=directions),
                        **updates,
                    )
                # Resolve unfamiliar names against the provider before asking
                # for more trip details. Familiar names are also rechecked by
                # search_hotels, including sales status, when search starts.
                import os
                from .ostrovok import CITIES

                destination = (spec.destination or "").strip().casefold().replace("ё", "е")
                if (
                    destination
                    and destination not in CITIES
                    and os.getenv("JOURNEY_DATA_SOURCE", "public") != "synthetic"
                ):
                    resolution = await resolve_destination(spec.destination, spec.country)
                    if resolution["status"] != "available":
                        raise DestinationUnavailable(spec.destination, resolution)
                questions = missing_hotel_questions(spec)
                if questions:
                    intro = "Учёл ваши пожелания. "
                    if any(age is None for age in spec.travellers.children):
                        count = len(spec.travellers.children)
                        children = (
                            "ребёнок"
                            if count == 1
                            else "ребёнка"
                            if count in {2, 3, 4}
                            else "детей"
                        )
                        adults = (
                            (
                                str(spec.travellers.adults)
                                + (
                                    " взрослый"
                                    if spec.travellers.adults == 1
                                    else " взрослых"
                                )
                                + " и "
                            )
                            if spec.travellers.adults
                            else ""
                        )
                        intro = f"В поездке {adults}{count} {children}. "
                    return result(
                        "needs_input", intro + questions[0], questions=questions, **updates
                    )
                # Reprice the chosen hotel for incremental edits; replacing it is an explicit search.
                road_change = bool(
                    state.selected_hotel
                    and spec.destination == state.trip_spec.destination
                    and spec.country == state.trip_spec.country
                    and intent.action not in {"replace_options", "restore_options"}
                    and intent.optimization != "cheaper"
                )
                progress(stage="searching", trip_spec=spec.model_dump(mode="json"))
                sources_start = time.monotonic()
                if journey.enabled(spec):
                    import os

                    synthetic = (
                        os.getenv("JOURNEY_DATA_SOURCE", "public") == "synthetic"
                    )
                    base["data_mode"] = (
                        "synthetic_journey"
                        if synthetic
                        else "public_hotels_estimated_journey"
                    )
                    from .transport import prepare_road, road_snapshot

                    if (
                        (
                            synthetic
                            and (
                                spec.origin != journey.CATALOGUE["origin"]
                                or spec.destination not in journey.ROUTES
                            )
                        )
                    ):
                        return result(
                            "no_solution",
                            "Для этого направления пока нет данных для полной дороги. Город сохранил. Можно изменить город отправления или продолжить только с отелем.",
                            **updates,
                        )
                    rail_reference = None
                    air_reference = None
                    if not synthetic:
                        from .tutu import prepare as prepare_rail
                        from .travelpayouts import prepare as prepare_air

                        _, rail_reference, air_reference = await asyncio.gather(
                            prepare_road(spec), prepare_rail(spec), prepare_air(spec)
                        )
                    metrics.tool_calls.append(
                        "journey_catalogue" if synthetic else "ostrovok_public_search"
                    )
                    if road_change and not synthetic:
                        from .public_content import recall

                        canonical = recall(state.selected_hotel["id"])
                        candidates, link = (
                            ([canonical], state.search_url)
                            if canonical
                            else ([], state.search_url)
                        )
                    else:
                        candidates, link = (
                            (journey.candidates(spec), None)
                            if synthetic
                            else await search_hotels(spec)
                        )
                        if road_change and synthetic:
                            candidates = [
                                h
                                for h in candidates
                                if h["id"] == state.selected_hotel["id"]
                            ]
                    if not synthetic:
                        from .public_content import remember

                        for h in candidates:
                            h["road_routes"] = road_snapshot(spec)
                            if rail_reference:
                                h["rail_reference"] = {
                                    spec.origin + "|" + spec.destination: rail_reference
                                }
                            if air_reference:
                                from .travelpayouts import key as air_key

                                h["air_reference"] = {air_key(spec): air_reference}
                            remember(h)
                    if spec.locked_hotel_id:
                        candidates = [
                            h for h in candidates if h["id"] == spec.locked_hotel_id
                        ]
                else:
                    metrics.tool_calls.append("ostrovok_public_search")
                    if road_change:
                        from .public_content import recall

                        canonical = recall(state.selected_hotel["id"])
                        candidates, link = (
                            ([canonical], state.search_url)
                            if canonical
                            else ([], state.search_url)
                        )
                    else:
                        candidates, link = await search_hotels(spec)
                progress(
                    stage="comparing",
                    trip_spec=spec.model_dump(mode="json"),
                    considered=len(candidates),
                )
                candidates = [
                    h for h in candidates if h["id"] not in spec.excluded_hotel_ids
                ]
                hotels, selection = select_hotels(
                    candidates,
                    spec,
                    intent.optimization == "cheaper",
                    include_conflicts=road_change,
                )
                if hotels and any(h.get("source_kind") == "public" for h in hotels):
                    from .public_content import enrich
                    from .trip_context import weather_context

                    ids = {h["id"] for h in hotels}
                    detailed = await asyncio.gather(
                        *(enrich(h) for h in candidates if h["id"] in ids)
                    )
                    hotels, detailed_selection = select_hotels(
                        detailed,
                        spec,
                        intent.optimization == "cheaper",
                        include_conflicts=road_change,
                    )
                    selection["matched"] = len(hotels)
                    selection["rejected"].update(detailed_selection["rejected"])
                    if hotels:
                        weather = await weather_context(hotels[0], spec)
                        from .places import nearby_places

                        for h in hotels:
                            h["weather"] = weather
                            h["nearby_places"] = nearby_places(h, spec)
                metrics.sources_ms += round((time.monotonic() - sources_start) * 1000)
                text = response_text(
                    hotels, selection, spec, patch, intent.optimization == "cheaper"
                )
                if intent.action == "replace_options":
                    text = (
                        "Показал другие варианты; прежние исключены, остальные пожелания сохранены. "
                        if hotels
                        else "Других подходящих отелей пока не осталось. Можно вернуть прежние или изменить условия. "
                    ) + text
                if journey.enabled(spec) and hotels:
                    text += (
                        " Стоимость предварительная."
                        if hotels[0].get("source_kind") == "public"
                        else " Время прибытия и заселения сверено."
                    )
                if (
                    intent.optimization == "cheaper"
                    and hotels
                    and state.hotel_options
                    and not patch
                ):
                    previous_prices = [
                        h.get("quote", {}).get("total_minor")
                        for h in state.hotel_options[:1]
                        if h.get("quote")
                    ]
                    previous_prices = [p for p in previous_prices if p]
                    new_price = hotels[0].get("quote", {}).get("total_minor")
                    if (
                        previous_prices
                        and new_price
                        and new_price >= min(previous_prices)
                    ):
                        text = (
                            "Более дешёвых вариантов с теми же условиями не нашёл. Сохранил ваши пожелания. "
                            + text
                        )
                return result(
                    "choosing" if hotels else "no_solution",
                    text,
                    hotel_options=hotels,
                    search_url=link,
                    selection=selection,
                    **updates,
                )
            questions = list(dict.fromkeys(intent.questions + missing_questions(spec)))
            if not spec.destination or (intent.action == "inspire" and not patch):
                destinations = await call("get_destination_options", spec)
                return result(
                    "needs_input" if questions else "choosing",
                    "Можно начать с направлений из каталога. Цены поездки потребуют уточнения условий.",
                    destination_options=destinations,
                    questions=questions,
                    **updates,
                )
            if questions:
                return result(
                    "needs_input",
                    "Уточним условия для расчёта поездки.",
                    questions=questions,
                    **updates,
                )
            if state.selected_plan and intent.action == "explain" and not patch:
                plan = await call("validate_plan", state.selected_plan, spec)
                valid = allowed(plan, spec)
                details = " ".join(c.message for c in plan.checks if c.status != "pass")
                return result(
                    "choosing" if valid else "no_solution",
                    (
                        "Выбранная поездка проверена инструментом. "
                        if valid
                        else "Выбранная поездка не отвечает всем условиям. "
                    )
                    + details
                    + " ".join(plan.tradeoffs),
                    options=[plan] if valid else [],
                    **updates,
                )
            if state.selected_plan:
                change = await call(
                    "propose_change",
                    state.selected_plan.id,
                    spec,
                    intent.optimization == "cheaper",
                )
                baseline, candidates = change.baseline, change.candidates
            else:
                candidates = await call("search_packages", spec)
            plans = [p for p in candidates if allowed(p, spec)][:3]
            if not state.selected_plan and intent.optimization == "cheaper":
                plans.sort(key=lambda plan: plan.total.amount_minor)
            if not plans:
                reasons = list(
                    dict.fromkeys(
                        c.message
                        for p in candidates
                        for c in p.checks
                        if c.status != "pass"
                    )
                )
                reason_text = (
                    " ".join(reasons[:4])
                    if reasons
                    else "Для указанного направления, дат и состава гостей в каталоге нет данных."
                )
                return result(
                    "no_solution",
                    "В доступном каталоге нет варианта, подтверждающего все условия. "
                    + reason_text
                    + " Можно обсудить другие даты, бюджет или требования; я их не менял.",
                    **updates,
                )
            if state.selected_plan:
                # A second independent validation is required before showing a proposal.
                plan = await call("validate_plan", plans[0], spec)
                if not allowed(plan, spec):
                    return result(
                        "no_solution",
                        "Предложенный вариант не прошёл повторную проверку условий.",
                        **updates,
                    )
                if (
                    intent.optimization == "cheaper"
                    and plan.total.amount_minor >= baseline.total.amount_minor
                ):
                    if plan.id == baseline.id:
                        return result(
                            "choosing",
                            "В доступном каталоге нет варианта дешевле выбранного. Текущая поездка соответствует условиям; её можно подтвердить заново.",
                            options=[plan],
                            **updates,
                        )
                    return result(
                        "no_solution",
                        "В доступном каталоге нет более дешёвого варианта, соответствующего новым условиям. Предыдущий выбор сохранён.",
                        **updates,
                    )
                changed = sorted(set(baseline.component_ids) ^ set(plan.component_ids))
                preserved = sorted(
                    set(baseline.component_ids) & set(plan.component_ids)
                )
                unchanged_fields = [
                    k for k in type(spec).model_fields if k not in patch
                ]
                preview = ChangePreview(
                    baseline_plan_id=baseline.id,
                    proposed_plan=plan,
                    changed=changed,
                    preserved=preserved + unchanged_fields,
                    price_delta=plan.total.amount_minor - baseline.total.amount_minor,
                    tradeoffs=plan.tradeoffs,
                    based_on_revision=state.revision,
                )
                return result(
                    "choosing",
                    "Подготовлено изменение поездки. Предыдущий выбор сохранён. "
                    "Проверьте и примите изменения перед учебным оформлением.",
                    change_preview=preview,
                    options=[plan],
                    **updates,
                )
            return result(
                "choosing",
                "Найдены варианты, соответствующие указанным условиям. "
                "Сравните состав цены, условия отмены и происхождение данных.",
                options=plans,
                **updates,
            )
    except (TimeoutError, ModelError) as exc:
        code = exc.code if isinstance(exc, ModelError) else "turn_timeout"
        messages = {
            "model_not_configured": "Подбор поездок временно недоступен. Попробуйте позже.",
            "model_configuration": "Подбор поездок временно недоступен. Попробуйте позже.",
            "model_credentials": "Подбор поездок временно недоступен. Попробуйте позже.",
            "model_unavailable": "Не удалось связаться с сервисом подбора. Попробуйте ещё раз немного позже.",
            "model_rate_limited": "Сейчас много запросов. Попробуйте немного позже.",
            "model_timeout": "Не успели подобрать поездку. Попробуйте повторить запрос.",
            "turn_timeout": "Время обработки запроса истекло. Попробуйте ещё раз.",
        }
        return result(
            "error",
            messages.get(
                code,
                "Не удалось понять запрос. Попробуйте описать пожелания другими словами.",
            )
            + (
                " Выбранная поездка сохранена; оформление по непроверенным условиям недоступно."
                if state.selected_plan
                else " Ваш запрос сохранён — его можно повторить."
            ),
            error_code=code,
        )
    except DestinationUnavailable as exc:
        text, question, suggestions = await destination_question(exc.name, exc.resolution)
        return result(
            "needs_input", text, questions=[question],
            selection={"destination_suggestions": suggestions},
            **(updates if "updates" in locals() else {}),
        )
    except ToolError as exc:
        # Preserve extracted intent for backend review, but never allow checkout.
        return result(
            "error",
            str(exc),
            error_code="tools_unavailable",
            **(updates if "updates" in locals() else {}),
        )

    except (ValidationError, TypeError, AttributeError, KeyError):
        return result(
            "error",
            "Не удалось обновить поездку. Ваш предыдущий выбор сохранён. Попробуйте ещё раз.",
            error_code="tool_invalid_response",
        )

import os
import asyncio
import json
import logging

from pydantic import ValidationError
from travel_agent.progress import progress_store, serve_progress
from travel_agent.domain import State, AgentTurn, Telemetry
from travel_agent.model import QwenModel, Settings, PROMPT_VERSION
from travel_agent.runner import run_turn, missing_questions
from travel_agent.tools import UnavailableTools, allowed, ToolError

import grpc
from concurrent import futures

from proto import predict_pb2
from proto import predict_pb2_grpc


class PredictorServicer(predict_pb2_grpc.PredictorServicer):
    def __init__(self, model=None, tools=None):
        self.model = model or QwenModel(Settings.from_env())
        if tools is None and os.getenv("AGENT_TOOLS_MODE", "unavailable") == "demo":
            from travel_agent.demo_tools import DemoTools
            tools = DemoTools()
        self.tools = tools if tools is not None else UnavailableTools()

    def RunTurn(self, request, context):
        if not request.caller:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "caller is required")
        try:
            state = State.model_validate_json(request.state_json or "{}")
        except (ValidationError, ValueError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid state")
        token = dict(context.invocation_metadata()).get("x-progress-token", "") if hasattr(context, "invocation_metadata") else ""
        remaining = context.time_remaining()
        turn = asyncio.run(run_turn(state, request.message, self.tools, self.model, timeout=max(.01, remaining - .25) if remaining is not None else None, progress=lambda **event: progress_store.put(token, **event)))
        progress_store.put(token, stage="complete", trip_spec=turn.trip_spec.model_dump(mode="json"))
        logging.info("agent_turn %s", json.dumps({"status": turn.status, "error_code": turn.error_code, **turn.telemetry.model_dump()}))
        return predict_pb2.TurnReply(turn_json=turn.model_dump_json(), caller=request.caller)

    def Evaluate(self, request, context):
        if not request.caller:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "caller is required")
        try:
            state = State.model_validate_json(request.state_json or "{}")
        except (ValidationError, ValueError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid state")
        async def evaluate():
            spec = state.trip_spec
            from travel_agent import journey
            if request.plan_id.startswith('content:'):
                from travel_agent.public_content import recall
                from travel_agent.trip_context import weather_context
                from travel_agent.places import nearby_places
                h=recall(request.plan_id.removeprefix('content:'))
                if h:
                    try:h['weather']=await asyncio.wait_for(weather_context(h,spec),timeout=9)
                    except TimeoutError:h['weather']={'kind':'seasonal','text':'Прогноз временно недоступен. Попробуйте ещё раз.','source_label':'Нет свежих данных'}
                    h['nearby_places']=nearby_places(h,spec)
                return AgentTurn(based_on_revision=state.revision,trip_spec=spec,status='choosing' if h else 'no_solution',assistant_message='Обновил сведения.',hotel_options=[h] if h else [],data_mode='public_catalogue',telemetry=Telemetry(model=self.model.settings.model,provider=self.model.settings.provider,prompt_version=PROMPT_VERSION))
            if state.search_mode == 'hotels' and journey.enabled(spec):
                from travel_agent.public_content import recall,remember
                from travel_agent.travelpayouts import prepare as prepare_air,key as air_key,valid_for
                canonical=recall(request.plan_id)
                if canonical and not spec.transport_owned and spec.transport_mode in {'auto','flight'}:
                    reference=(canonical.get('air_reference') or {}).get(air_key(spec))
                    if not reference or not valid_for(reference,spec):
                        try:fresh=await asyncio.wait_for(prepare_air(spec),timeout=4)
                        except TimeoutError:fresh=None
                        if fresh:canonical['air_reference']={air_key(spec):fresh};remember(canonical)
                hotel = journey.reprice(spec, request.plan_id)
                return AgentTurn(based_on_revision=state.revision, trip_spec=spec,
                                 status='choosing' if hotel else 'no_solution',
                                 assistant_message='Пересчитал поездку и проверил состыковки.' if hotel else 'Этот вариант недоступен с новыми условиями.',
                                 hotel_options=[hotel] if hotel else [], data_mode='public_hotels_estimated_journey' if hotel and hotel.get('source_kind')=='public' else 'synthetic_journey',
                                 telemetry=Telemetry(model=self.model.settings.model, provider=self.model.settings.provider, prompt_version=PROMPT_VERSION))
            questions = missing_questions(spec)
            options, destinations = [], []
            status, message = "needs_input", "Уточните условия поездки."
            if not spec.destination:
                destinations = await self.tools.get_destination_options(spec)
            elif not questions:
                candidates = await self.tools.search_packages(spec)
                options = [p for p in candidates if allowed(p, spec) and (not request.plan_id or p.id == request.plan_id)][:3]
                if request.plan_id and options:
                    validated = await self.tools.validate_plan(options[0], spec)
                    options = [validated] if allowed(validated, spec) else []
                status = "choosing" if options else "no_solution"
                message = "Учебные варианты проверены по текущим условиям." if options else "В учебном каталоге нет подходящих данных для этих условий."
            return AgentTurn(based_on_revision=state.revision, trip_spec=spec, status=status,
                             assistant_message=message, questions=questions, options=options,
                             destination_options=destinations, data_mode=self.tools.data_mode,
                             telemetry=Telemetry(model=self.model.settings.model, provider=self.model.settings.provider,
                                                 prompt_version=PROMPT_VERSION, tool_calls=["evaluate"]))
        try:
            turn = asyncio.run(asyncio.wait_for(evaluate(), timeout=5))
        except (ToolError, TimeoutError, ValidationError):
            context.abort(grpc.StatusCode.UNAVAILABLE, "catalogue unavailable")
        return predict_pb2.TurnReply(turn_json=turn.model_dump_json(), caller=request.caller)

    def Predict(self, request, context):
        name = request.name.strip() or "friend"
        caller = request.caller or "unknown"
        message = f"hello {name} from agent"
        return predict_pb2.PredictReply(message=message, caller=caller)


def serve() -> None:
    logging.basicConfig(level=logging.INFO)
    if os.getenv('MODEL_WARMUP', '0') == '1':
        from travel_agent.warmup import warmup
        # Readiness follows real prefill, so the first user's request is warm too.
        asyncio.run(warmup())
    port = os.getenv("AGENT_PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    predict_pb2_grpc.add_PredictorServicer_to_server(PredictorServicer(), server)
    server.add_insecure_port(f"{os.getenv('AGENT_BIND_HOST', '[::]')}:{port}")
    progress_server = serve_progress(int(os.getenv("AGENT_PROGRESS_PORT", "15052")))
    server.start()
    print(f"agent gRPC server running on :{port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()

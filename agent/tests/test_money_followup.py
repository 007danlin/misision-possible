import unittest
from travel_agent.domain import State,apply_intent
from travel_agent.money_followup import money_followup


def waiting(**updates):
    return State(search_mode='hotels',trip_spec={'origin':'Москва','destination':'Сочи','budget':{'amount_minor':12000000},'budget_scope':'whole_trip','include_transport':True,'travellers':{'adults':2,'children':[7]},'dates':{'start':'2026-11-10','end':'2026-11-15'}},**({'assistant_message':'Сколько из общего бюджета оставить на питание и личные расходы?'}|updates))


class MoneyFollowupTests(unittest.TestCase):
    def test_reserve_answers_never_change_trip_budget_or_guests(self):
        cases=[('0',0),('10000',1000000),('10 тысяч',1000000),('15 000 рублей',1500000),('12,5 тыс. рублей',1250000),('Оставим 12,5 тысяч рублей на еду',1250000),('без резерва',0),('Без отдельного резерва',0),('Ничего не оставляем отдельно',0)]
        for questions in ([],['Сколько из общего бюджета оставить на питание и личные расходы?']):
            for message,amount in cases:
                with self.subTest(message=message,questions=questions):
                    state=waiting(questions=questions)
                    intent=money_followup(state,message)
                    self.assertIsNotNone(intent)
                    new=apply_intent(state.trip_spec,intent,message)
                    self.assertEqual(new.expense_reserve.amount_minor,amount)
                    self.assertEqual(new.model_dump(exclude={'expense_reserve'}),state.trip_spec.model_dump(exclude={'expense_reserve'}))

    def test_amount_is_not_a_reserve_when_a_different_question_is_pending(self):
        for question in ['Из какого города отправляетесь?','Какой бюджет на всю поездку?','Сколько лет ребёнку?']:
            state=waiting(questions=[question])
            self.assertIsNone(money_followup(state,'15 тысяч рублей'))

    def test_new_budget_complex_and_foreign_currency_requests_are_not_swallowed(self):
        for message in ['Бюджет на всю поездку 100 тысяч рублей','10 или 15 тысяч','Не 10 тысяч','10 тысяч, добавь бассейн','200 долларов','-1000','500 евро','10 тысяч на отель','0,001 рубля']:
            self.assertIsNone(money_followup(waiting(),message),message)

if __name__ == "__main__":
    unittest.main()

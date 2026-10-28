import unittest
from travel_agent.domain import Intent,TripSpec,apply_intent
from travel_agent.grounding import ground_intent


class BudgetFollowups(unittest.TestCase):
    def test_explicit_total_resets_previous_nightly_period_when_model_omits_it(self):
        old=TripSpec(destination='Сочи',budget={'amount_minor':1250000},budget_period='night',budget_scope='hotel',travellers={'adults':2,'children':[7]},dates={'start':'2026-11-10','end':'2026-11-15'})
        for text in ['Давай 70 000 рублей за всё проживание','70 тысяч рублей за весь отдых','Лимит 70 тысяч рублей за весь срок','Не больше 70 тысяч рублей за весь отдых','Не за ночь, 70 тысяч рублей за всё проживание']:
            intent=Intent(patch={'budget':{'amount_minor':7000000}},evidence={'budget':text})
            new=apply_intent(old,ground_intent(intent,text,old),text)
            self.assertEqual(new.budget_period,'stay')
            self.assertEqual(new.budget.amount_minor,7000000)
            self.assertEqual(new.travellers,old.travellers)
            self.assertEqual(new.dates,old.dates)

    def test_cheaper_does_not_authorize_excluding_the_whole_displayed_list(self):
        for text in ['Подешевле, бассейн и парковку сохрани','Можно дешевле, остальное оставь','Найди дешевле']:
            intent=Intent(action='replace_options',optimization='cheaper',evidence={'optimization':text})
            fixed=ground_intent(intent,text,TripSpec())
            self.assertEqual(fixed.action,'change')
            self.assertEqual(fixed.optimization,'cheaper')

    def test_cheaper_with_explicit_replacement_still_replaces(self):
        for text in ['Все эти мимо, покажи другие подешевле','Замени всю подборку, хочу дешевле','Ни один не подходит, давай дешевле']:
            intent=Intent(action='replace_options',optimization='cheaper',evidence={'optimization':text})
            self.assertEqual(ground_intent(intent,text,TripSpec()).action,'replace_options')

if __name__ == "__main__":
    unittest.main()

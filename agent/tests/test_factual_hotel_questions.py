import unittest
from travel_agent.domain import State,Intent,TripSpec,apply_intent
from travel_agent.fast_intent import protect_hotel_question,clarify_ambiguous_request
from travel_agent.hotel_selection import explain_hotels


class FactualHotelQuestions(unittest.TestCase):
    def test_pet_permission_question_cannot_create_a_mandatory_pet_filter(self):
        for text in ['А можно с собакой в этот отель?','Можно приехать с питомцем в выбранный отель?','Пускают ли с кошкой во второй отель?']:
            wrong=Intent(action='change',patch={'hard_constraints':{'pets':True}},evidence={'hard_constraints':text})
            fixed=protect_hotel_question(wrong,text)
            old=TripSpec(hotel_preferences={'pool':True})
            self.assertEqual(fixed.action,'explain')
            self.assertEqual(apply_intent(old,fixed,text),old)

    def test_actual_pet_request_still_changes_the_search(self):
        text='Найди отель, куда можно с собакой'
        intent=Intent(patch={'hard_constraints':{'pets':True}},evidence={'hard_constraints':text})
        self.assertTrue(protect_hotel_question(intent,text).patch.hard_constraints.pets)

    def test_answers_distinguish_catalogue_flags_from_confirmed_supplier_terms(self):
        h={'name':'Первый отель','amenity_codes':['has_pets'],'quote':{'total_minor':3000000,'nightly_minor':600000,'breakfast':False}}
        answer=explain_hotels([h],1,'Можно с собакой?')
        self.assertIn('В каталоге',answer)
        self.assertIn('нужно подтвердить',answer)
        h['amenity_codes']=[]
        self.assertIn('не подтверждено',explain_hotels([h],1,'Можно с собакой?'))
        self.assertIn('завтрак не учтён',explain_hotels([h],1,'А завтрак включён?'))

    def test_undecided_destinations_do_not_replace_the_saved_trip(self):
        old=TripSpec(destination='Сочи',budget={'amount_minor':12000000})
        for text in ['В Питер или Казань, не могу выбрать','Лучше Москва либо Сочи?']:
            intent=clarify_ambiguous_request(text)
            self.assertIsNotNone(intent)
            self.assertTrue(intent.questions)
            self.assertEqual(apply_intent(old,intent,text),old)
        self.assertIsNone(clarify_ambiguous_request('Питер или Санкт-Петербург'))

if __name__=='__main__':unittest.main()

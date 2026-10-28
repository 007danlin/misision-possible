import json,unittest
from travel_agent.domain import Intent,TripSpec,apply_intent,State
from travel_agent.fast_intent import fast_intent
from travel_agent.model import canonical_intent
from travel_agent.grounding import ground_intent


class HardConstraintRemoval(unittest.TestCase):
    def test_misplaced_cancel_removal_preserves_semantics_and_evidence(self):
        text='Можно и без бесплатной отмены'
        old=TripSpec(hard_constraints={'free_cancellation':True,'pets':True})
        for evidence in (text,{'remove_hotel_preferences':text}):
            raw=json.dumps({'action':'change','remove_hotel_preferences':['cancel'],'evidence':evidence},ensure_ascii=False)
            intent=Intent.model_validate_json(canonical_intent(raw,text))
            new=apply_intent(old,ground_intent(intent,text,old),text)
            self.assertFalse(new.hard_constraints.free_cancellation)
            self.assertTrue(new.hard_constraints.pets)

    def test_conflicting_removal_is_not_silently_selected(self):
        with self.assertRaises(ValueError):
            canonical_intent(json.dumps({'remove_hotel_preferences':['cancel'],'hard_constraints':{'free_cancellation':True}}))

    def test_own_car_is_a_travel_mode_not_already_bought_tickets(self):
        old=TripSpec(origin='Москва',destination='Сочи',transport_mode='train',transport_owned=True,travellers={'adults':2,'children':[7]})
        for text in ['На своей машине','На машине','На своём автомобиле','Лучше на своей машине']:
            intent=fast_intent(State(search_mode='hotels',trip_spec=old),text)
            new=apply_intent(old,intent,text)
            self.assertEqual(new.transport_mode,'car')
            self.assertFalse(new.transport_owned)
            self.assertTrue(new.include_transport)
            self.assertEqual(new.travellers,old.travellers)

if __name__=='__main__':unittest.main()

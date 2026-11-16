import unittest
from review_rules import QUESTIONS,FUNCTIONAL_PROFILES,profile_questions,assess_company_rules,assess_review,normalize,comparison_scope

def financial(flag=False,rules=None,feature='net_margin_pct'):
    return {'status':'SCORED','financial_screening_flag':flag,'largest_masked_error_feature':feature,'financial_rules':{'rules':rules or []}}

def answered_no(profile='Routine entity'):
    return {**{key:'No' for key,_,_,_ in QUESTIONS+profile_questions(profile)},'functional_profile':profile,'related_party_transactions':'Yes','functional_context_verified':'Yes','commercial_explanation_supported':'No'}

class ReviewRulesTests(unittest.TestCase):
    def test_source_accounting_warning_is_separate_from_completed_rule_result(self):
        data=financial();data['financial_rules']['source_gross_profit_review']=True
        answers=answered_no();answers['commercial_explanation_supported']='Yes'
        result=assess_review(data,answers,{'commercial_explanation':'A generic commercial explanation'})
        self.assertEqual(result['concern'],'Less concern')
        self.assertTrue(any('accounting review' in note for note in result['financial_context_warnings']))
        self.assertFalse(result['financial_model_flag'])
    def test_default_unknown_is_not_low_concern(self):
        result=assess_review(financial(),{})
        self.assertEqual(result['concern'],'More information needed');self.assertIn('functional_profile',result['unknown_criteria'])
        self.assertIsNone(result['screening_flag'])
    def test_all_known_no_and_no_financial_trigger_is_provisional_less_concern(self):
        result=assess_review(financial(),answered_no())
        self.assertEqual(result['concern'],'Less concern');self.assertEqual(result['tp_compliance'],'NOT_DETERMINED')
    def test_yes_remains_raised_when_other_context_is_unknown(self):
        answers=answered_no();answers.update(intangibles_low_reward='Yes',restructuring_reward_change='Yes')
        result=assess_review(financial(),answers,{'supporting_notes':'Contracts and ownership reviewed by the analyst.'})
        self.assertEqual(result['concern'],'Higher concern')
        answers['related_party_transactions']='Unknown information'
        self.assertEqual(assess_review(financial(),answers)['concern'],'Higher concern')
    def test_one_financing_topic_is_enough_when_answered_yes(self):
        answers=answered_no();answers.update(disproportionate_borrowing='Yes',interest_service_concern='Yes')
        self.assertEqual(assess_review(financial(),answers)['concern'],'Higher concern')
    def test_model_anomaly_does_not_change_independent_rule_result(self):
        result=assess_review(financial(True),answered_no())
        self.assertEqual(result['concern'],'Less concern');self.assertTrue(result['financial_model_flag'])
        self.assertTrue(result['financial_context_warnings'])
    def test_model_and_different_documented_topic_can_raise_review_priority(self):
        answers=answered_no();answers['low_tax_related_party']='Yes'
        self.assertEqual(assess_review(financial(True),answers,{'supporting_notes':'Counterparty, territory and transactions identified'})['concern'],'Higher concern')
    def test_financial_trigger_is_retained_when_commercially_explained(self):
        answers=answered_no();answers['commercial_explanation_supported']='Yes'
        result=assess_review(financial(True),answers,{'commercial_explanation':'Documented product launch and approved business plan'})
        self.assertEqual(result['concern'],'Less concern');self.assertTrue(result['financial_model_flag'])
    def test_unknown_remaining_facts_prevent_lower_concern(self):
        answers=answered_no();answers['stock_decline']='Unknown information'
        self.assertEqual(assess_review(financial(),answers)['concern'],'More information needed')
    def test_unavailable_model_does_not_prevent_independent_rule_assessment(self):
        result=assess_review({'status':'ABSTAIN','financial_screening_flag':None,'reason':'Unsupported peer pool'},answered_no())
        self.assertEqual(result['concern'],'Less concern');self.assertIsNone(result['financial_model_flag'])
        self.assertTrue(result['financial_context_warnings'])
    def test_contradiction_is_visible_without_hiding_a_yes_indicator(self):
        answers=answered_no();answers.update(related_party_transactions='No',low_tax_related_party='Yes')
        result=assess_review(financial(),answers)
        self.assertEqual(result['concern'],'Higher concern');self.assertTrue(result['consistency_warnings'])
    def test_single_yes_needs_no_notes_or_second_topic(self):
        answers=answered_no();answers['intangibles_low_reward']='Yes'
        result=assess_review(financial(),answers)
        self.assertEqual(result['concern'],'Higher concern');self.assertTrue(result['screening_flag'])
        self.assertFalse(result['notes_provided'])
        self.assertEqual(result['positive_analyst_indicators'],['intangibles_low_reward'])
    def test_each_profile_has_a_specific_risk_question_that_can_trigger(self):
        for profile in list(FUNCTIONAL_PROFILES)[1:]:
            with self.subTest(profile=profile):
                answers=answered_no(profile);key=profile_questions(profile)[-1][0];answers[key]='Yes'
                result=assess_company_rules(answers)
                self.assertEqual(result['concern'],'Higher concern');self.assertIn(key,result['positive_analyst_indicators'])
    def test_profile_and_background_yes_are_not_risk_indicators(self):
        for profile in list(FUNCTIONAL_PROFILES)[1:]:
            answers=answered_no(profile);answers['commercial_explanation_supported']='Yes'
            result=assess_company_rules(answers)
            self.assertEqual(result['concern'],'Less concern');self.assertFalse(result['screening_flag'])
    def test_nonapplicable_old_profile_answer_is_ignored(self):
        answers=answered_no('Routine entity');answers['risk_taker_low_reward']='Yes'
        self.assertEqual(assess_company_rules(answers)['concern'],'Less concern')
    def test_risk_yes_raises_concern_even_with_unknown_profile_and_no_model(self):
        result=assess_review({'status':'ABSTAIN','financial_screening_flag':None},{'noncommercial_transactions':'Yes'})
        self.assertEqual(result['concern'],'Higher concern');self.assertTrue(result['screening_flag'])
    def test_rule_result_is_invariant_to_all_financial_model_states(self):
        for answers in [answered_no(),{**answered_no(),'noncommercial_transactions':'Yes'},{}]:
            expected=assess_company_rules(answers)
            for model in [financial(False),financial(True),{'status':'ABSTAIN','financial_screening_flag':None},
                          {'status':'SCORED','financial_screening_flag':False,'financial_rules':{'source_gross_profit_review':True}}]:
                actual=assess_review(model,answers)
                for key in ['concern','screening_flag','positive_analyst_indicators','rule_id']:
                    self.assertEqual(actual[key],expected[key])
    def test_unknown_and_invalid_values(self):
        self.assertEqual(normalize(None),'Unknown information')
        with self.assertRaises(ValueError):normalize('probably')
    def test_unrepresented_code_or_pool_uses_exact_user_copy(self):
        represented={'printing':{'18111'}}
        self.assertTrue(comparison_scope('printing','18111',represented)['eligible'])
        self.assertFalse(comparison_scope('printing','99999',represented)['eligible'])
        result=comparison_scope('OTHER','18111',represented)
        self.assertEqual(result['message'],'This company cannot be compared with the current peer pool.')
        self.assertEqual(result['display_status'],'Not assessed')

if __name__=='__main__':unittest.main()

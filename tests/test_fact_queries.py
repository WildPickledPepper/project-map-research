import unittest
from adapters.fact_queries import find_path


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.g={'nodes':[{'id':i} for i in 'abcd'],'edges':[
            {'source':'a','target':'b','kind':'call','status':'candidate','evidence':['x']},
            {'source':'b','target':'a','kind':'call'},
            {'source':'b','target':'c','kind':'call'},
            {'source':'c','target':'d','kind':'binding'}]}

    def test_cycle_reverse_and_candidate_payload(self):
        r=find_path(self.g,'c','a',{'call'},reverse=True)
        self.assertEqual([n['id'] for n in r['nodes']],['c','b','a'])
        self.assertEqual(r['edges'][1]['status'],'candidate')
        self.assertEqual(r['edges'][1]['evidence'],['x'])

    def test_depth_limit_and_kind_filter_are_visible(self):
        r=find_path(self.g,'a','c',{'call'},max_depth=1)
        self.assertFalse(r['found']);self.assertTrue(r['depth_limit_reached'])
        r=find_path(self.g,'a','d',{'call'})
        self.assertFalse(r['found']);self.assertFalse(r['depth_limit_reached'])

    def test_absent_endpoint_is_an_error(self):
        with self.assertRaises(ValueError):find_path(self.g,'a','missing',{'call'})

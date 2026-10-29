import unittest
import numpy as np,pandas as pd
from rdm_design import design,external_path,assumptions,features
from rdm_analyze import metrics,jaccard,mask_rules,fit_boxes
from simulation import *

class RDMTests(unittest.TestCase):
    def test_design_reproducible_and_seed_distinct(self):
        self.assertEqual(design(16,1,'main'),design(16,1,'main'))
        self.assertNotEqual(design(16,1,'main'),design(16,2,'main'))
    def test_latin_cagr_strata(self):
        xs=design(100,8,'main');bins=[int((x['cagr']+.3)/.75*100) for x in xs]
        self.assertEqual(sorted(bins),list(range(100)))
    def test_cash_legal_and_stock_permission_separate(self):
        x=design(1,1,'main')[0];x['legal_regime']='zero';a=assumptions(x,'face')
        self.assertEqual(a.cash_legal_capacity_per_year,0);self.assertTrue(a.stock_dividends_permitted)
    def test_no_split_or_id_leakage(self):
        x=design(1,1,'main')[0];x['split']='train';f=features(x)
        self.assertFalse(set(f)&{'id','split','phase','path_seed'})
    def test_metrics_and_empty_jaccard(self):
        m=metrics([1,1,0,0],[1,0,1,0]);self.assertEqual(m['density'],.5);self.assertEqual(m['coverage'],.5)
        self.assertIsNone(jaccard([0,0],[0,0]));self.assertEqual(jaccard([1,0],[1,1]),.5)
    def test_rules_do_not_impose_training_extrema(self):
        x=pd.DataFrame({'a':[-100,0,1,100]});m=mask_rules(x,[{'a':{'lo':None,'hi':.5}}])
        self.assertEqual(m.tolist(),[True,True,False,False])
    def test_prim_recovers_simple_rectangle(self):
        rng=np.random.default_rng(45);x=pd.DataFrame(rng.random((400,2)),columns=['a','b']);y=((x.a<.4)&(x.b>.4)).to_numpy()
        rules,status=fit_boxes(x,y);m=metrics(mask_rules(x,rules),y)
        self.assertEqual(status,'fitted');self.assertGreaterEqual(m['density'],.8);self.assertGreaterEqual(m['coverage'],.7)
    def test_constant_target_is_explicit(self):
        x=pd.DataFrame({'a':[0,1,2]});self.assertEqual(fit_boxes(x,np.ones(3,bool)),([],'constant_target'))

if __name__=='__main__':unittest.main()

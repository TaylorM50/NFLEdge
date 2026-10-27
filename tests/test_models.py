import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from context import snap_report,eligible,apply_context
from players import quantile
class Tests(unittest.TestCase):
    def test_no_invented_snap_cap(self):
        self.assertEqual(snap_report('Questionable with an ankle injury')['kind'],'unknown')
        self.assertEqual(snap_report('He will not be on a snap count')['kind'],'unresolved')
        self.assertEqual(snap_report('He is limited to 20-25 snaps')['high'],25)
    def test_conformal_quantile(self):
        self.assertEqual(quantile(range(1,10)),8)
        self.assertIsNone(quantile([]))
    def test_provenance_expiry(self):
        now=datetime.now(timezone.utc)
        row={'game_id':'g','source_url':'https://example.org','as_of':(now-timedelta(hours=1)).isoformat(),'expires_at':(now+timedelta(hours=1)).isoformat()}
        event={'game_id':'g','kickoff':(now+timedelta(days=1)).isoformat()}
        self.assertTrue(eligible(row,event))
        row['expires_at']=(now-timedelta(seconds=1)).isoformat();self.assertFalse(eligible(row,event))
    @patch('context.weather',return_value={'state':'unknown'})
    @patch('context.local')
    def test_injury_changes_forecast_only_with_identity_and_role(self,local,weather):
        now=datetime.now(timezone.utc)
        r={'game_id':'g','team':'ATL','player_id':'pid','name':'Test player','source_url':'https://example.org','as_of':(now-timedelta(hours=1)).isoformat(),'expires_at':(now+timedelta(days=1)).isoformat(),'replacement_drop_points':4,'availability':None}
        local.side_effect=lambda name,default: {'personnel.json':[r],'matchups.json':[],'player_ids.json':{'pid':'123'}}.get(name,default)
        game={'id':'g','home':'ATL','away':'SF','home_probability':.5,'margin':0}
        event={'espn_id':'e','kickoff':(now+timedelta(hours=3)).isoformat()}
        injury={'state':'ok','rows':[{'team':'ATL','espn_id':'123','status':'Out'}]}
        result=apply_context(game,event,injury,[])
        self.assertLess(result['scenario_probability'],.5)
        self.assertEqual(result['context']['point_delta_home'],-4)
        injury['rows'][0]['status']='Questionable'
        self.assertEqual(apply_context(game,event,injury,[])['context']['point_delta_home'],0)
if __name__=='__main__':unittest.main()

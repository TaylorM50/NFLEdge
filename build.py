import json
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression,Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score,brier_score_loss
from context import injuries,upcoming_events,apply_context
from players import build_player_models

BASE='https://github.com/nflverse/nflverse-data/releases/download'
now=datetime.now(timezone.utc);year=now.year if now.month>=8 else now.year-1
out=Path('public');out.mkdir(exist_ok=True)
def norm(x):return {'LA':'LAR','OAK':'LV','SD':'LAC','STL':'LAR','WSH':'WAS'}.get(x,x)
def tidy(x):
    if isinstance(x,dict):return {str(k):tidy(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [tidy(v) for v in x]
    if isinstance(x,(np.integer,)):return int(x)
    if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
    if isinstance(x,np.bool_):return bool(x)
    if x is None:return None
    if pd.isna(x):return None
    return x

def main():
    s=pd.read_csv(BASE+'/schedules/games.csv',low_memory=False)
    s=s[s.season.between(year-5,year)].copy();s.gameday=pd.to_datetime(s.gameday)
    for c in ['home_team','away_team']:s[c]=s[c].map(norm)
    s=s.sort_values(['gameday','game_id']);parts=[];warnings=[]
    for yr in range(year-5,year+1):
        try:
            p=pd.read_parquet(f'{BASE}/pbp/play_by_play_{yr}.parquet')
            p=p[p.play_type.isin(['pass','run'])&p.epa.notna()].copy()
            p.posteam=p.posteam.map(norm);p.defteam=p.defteam.map(norm);parts.append(p)
        except Exception as e:
            if yr==year:raise RuntimeError('Current-season play-by-play required') from e
            warnings.append(f'{yr}: {type(e).__name__}')
    p=pd.concat(parts,ignore_index=True)
    p['success']=(p.epa>0).astype(float);p['explosive']=((p.play_type.eq('pass')&p.yards_gained.ge(20))|(p.play_type.eq('run')&p.yards_gained.ge(10))).astype(float)
    p['turnovers']=p.interception.fillna(0)+p.fumble_lost.fillna(0);p['is_pass']=p.play_type.eq('pass').astype(float)
    agg=p.groupby(['game_id','posteam']).agg(epa=('epa','mean'),success=('success','mean'),explosive=('explosive','mean'),turnover=('turnovers','mean'),pass_share=('is_pass','mean'))
    for kind in ['pass','run']:agg[kind+'_epa']=p[p.play_type.eq(kind)].groupby(['game_id','posteam']).epa.mean()
    cols=['epa','success','explosive','turnover','pass_epa','run_epa','pass_share'];baseline=np.array([0,.42,.10,.025,0,0,.6]*2)
    history={};snapshots={};rows=[];ys=[];ms=[];ds=[];ids=[]
    def profile(t):
        h=history.get(t,[])[-16:]
        if not h:return baseline.copy()
        v=np.average(np.array(h),axis=0,weights=.9**np.arange(len(h)-1,-1,-1))
        return (v*len(h)+baseline*4)/(len(h)+4)
    def feature(h,a,neutral):return np.r_[h-a,0 if neutral else 1]
    for day,group in s.groupby('gameday',sort=True):
        for _,g in group.iterrows():
            h,a=profile(g.home_team),profile(g.away_team);neutral=str(g.get('location','')).lower()=='neutral'
            snapshots[g.game_id]=(h.copy(),a.copy(),neutral)
            if pd.notna(g.home_score) and pd.notna(g.away_score) and g.home_score!=g.away_score:
                rows.append(feature(h,a,neutral));ys.append(int(g.home_score>g.away_score));ms.append(g.home_score-g.away_score);ds.append(day);ids.append(g.game_id)
        for _,g in group.iterrows():
            if pd.isna(g.home_score) or pd.isna(g.away_score):continue
            for t,o in [(g.home_team,g.away_team),(g.away_team,g.home_team)]:
                if (g.game_id,t) in agg.index and (g.game_id,o) in agg.index:
                    vals=np.r_[agg.loc[(g.game_id,t),cols].values.astype(float),agg.loc[(g.game_id,o),cols].values.astype(float)]
                    history.setdefault(t,[]).append(np.where(np.isfinite(vals),vals,baseline))
    X=np.array(rows);y=np.array(ys);m=np.array(ms);dates=pd.to_datetime(ds)
    if len(y)<300:raise RuntimeError('Insufficient training games')
    def fit(mask):
        return (make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=2000)).fit(X[mask],y[mask]),make_pipeline(StandardScaler(),Ridge(alpha=100)).fit(X[mask],m[mask]))
    saved={};folds=[];allpr=[];ally=[]
    for season in range(year-2,year+1):
        train=dates<pd.Timestamp(f'{season}-08-01');test=(dates>=pd.Timestamp(f'{season}-08-01'))&(dates<pd.Timestamp(f'{season+1}-08-01'))
        if train.sum()<250 or not test.any():continue
        clf,reg=fit(train);pr=clf.predict_proba(X[test])[:,1];mar=reg.predict(X[test]);allpr.extend(pr);ally.extend(y[test])
        folds.append({'season':season,'games':int(test.sum()),'accuracy':accuracy_score(y[test],pr>=.5),'brier':brier_score_loss(y[test],pr)})
        for i,b,z in zip(np.where(test)[0],pr,mar):saved[ids[i]]=(float(b),float(z))
    clf,reg=fit(np.ones(len(y),bool));current=p[p.season.eq(year)];teams=[]
    for t,o in current.dropna(subset=['posteam']).groupby('posteam'):
        d=current[current.defteam.eq(t)];pa=o[o.play_type.eq('pass')]
        teams.append({'team':t,'epa':o.epa.mean(),'def_epa':d.epa.mean(),'success':o.success.mean(),'explosive':o.explosive.mean(),'turnover':o.turnovers.mean(),'sack_rate':pa.sack.fillna(0).mean(),'pass_share':o.is_pass.mean(),'plays':len(o)})
    teams.sort(key=lambda t:t['epa'],reverse=True)
    players,intervals=build_player_models(p,s,year)
    injury=injuries()
    try:events=upcoming_events()
    except Exception as e:events=[];warnings.append('ESPN events: '+str(e))
    games=[]
    for _,g in s[s.season.eq(year)].iterrows():
        done=pd.notna(g.home_score) and pd.notna(g.away_score)
        h,a,neutral=snapshots[g.game_id]
        if done:
            if g.game_id not in saved:continue
            prob,margin=saved[g.game_id]
        else:
            h,a=profile(g.home_team),profile(g.away_team);z=feature(h,a,neutral).reshape(1,-1)
            prob=float(clf.predict_proba(z)[0,1]);margin=float(reg.predict(z)[0])
        game={'id':g.game_id,'week':int(g.week),'date':str(g.gameday.date()),'home':g.home_team,'away':g.away_team,'home_score':g.home_score,'away_score':g.away_score,'complete':done,'home_probability':prob,'margin':margin,'home_pass_share':h[6],'away_pass_share':a[6],'analysis':[]}
        for t,v,w in [(g.home_team,h,a),(g.away_team,a,h)]:
            game['analysis'].append({'team':t,'pass_index':v[4]+w[11],'run_index':v[5]+w[12],'turnover_rate':v[3],'opponent_takeaway_rate':w[10],'explosive_allowed':v[9],'note':'Prior weighted team profiles; additive matchup indices are directional, not predicted EPA.'})
        if not done:
            event=next((e for e in events if e['home']==g.home_team and e['away']==g.away_team and abs((pd.Timestamp(e['kickoff']).tz_convert(None).normalize()-g.gameday).days)<=1),None)
            game=apply_context(game,event,injury,players)
        else:
            observed=current[current.game_id.eq(g.game_id)]
            game['actual']=[{'team':t,'epa':q.epa.mean(),'success':q.success.mean(),'explosive':q.explosive.mean(),'turnovers':q.turnovers.sum()} for t,q in observed.groupby('posteam')]
            game['context']={'state':'historical_context_unavailable','reason':'Current injuries/weather are never applied to historical games'}
        games.append(game)
    data={'generated':now.isoformat(),'season':year,'last_pbp_week':int(current.week.max()),'teams':teams,'games':games,'players':players,'interval_validation':intervals,'injuries':injury,'validation':{'games':len(ally),'accuracy':accuracy_score(ally,np.array(allpr)>=.5) if ally else None,'brier':brier_score_loss(ally,allpr) if ally else None,'folds':folds,'scope':'Base team models only. Season-forward historical reconstruction, not frozen live forecast record. No context-overlay accuracy claim.'},'warnings':warnings}
    if len(teams)!=32:raise RuntimeError('Expected all 32 teams; refusing incomplete publication')
    (out/'data.json').write_text(json.dumps(tidy(data),allow_nan=False))
    (out/'index.html').write_text(Path('index.html').read_text())
    (out/'health.json').write_text(json.dumps({'ok':True,'generated':now.isoformat(),'injuries_state':injury['state']}))
    print(f'Built {len(games)} games, {len(players)} player forecasts')
if __name__=='__main__':main()

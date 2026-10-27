"""Chronological split-conformal baseline intervals with untouched temporal test."""
import math
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SPECS=[('passing_yards','passer_player_id','passer_player_name','pass_attempt'),('rushing_yards','rusher_player_id','rusher_player_name','rush_attempt'),('receiving_yards','receiver_player_id','receiver_player_name','pass_attempt')]

def quantile(scores,alpha=.2):
    a=np.sort(np.asarray(scores,float));k=math.ceil((len(a)+1)*(1-alpha))
    if len(a)==0 or k>len(a):return None
    return float(a[k-1])

def build_player_models(pbp,schedule,year):
    projections=[];reports=[]
    dates=schedule.set_index('game_id').gameday.to_dict()
    for stat,idcol,namecol,opcol in SPECS:
        p=pbp[pbp[opcol].eq(1)&pbp[idcol].notna()].copy()
        g=p.groupby(['game_id',idcol,'posteam'],sort=False).agg(y=(stat,'sum'),opps=(idcol,'size'),name=(namecol,'last'),season=('season','first')) .reset_index()
        g['day']=g.game_id.map(dates);g=g.dropna(subset=['day']).sort_values(['day','game_id'])
        history={};rows=[];target=[];seasons=[];meta=[]
        def feat(h):
            z=h[-4:];ys=[a[0] for a in z];vol=[a[1] for a in z]
            return [np.mean(ys),np.mean(vol),ys[-1],np.std(ys),len(z)]
        for _,r in g.iterrows():
            pid=r[idcol];h=history.setdefault(pid,[])
            if len(h)>=2:
                rows.append(feat(h));target.append(float(r.y));seasons.append(int(r.season));meta.append((pid,r.posteam,r['name'],r.day))
            h.append((float(r.y),float(r.opps)))
        X=np.asarray(rows,float);y=np.asarray(target,float);ss=np.asarray(seasons)
        train=ss<year-1;cal=ss==year-1;test=ss==year
        report={'stat':stat,'target_coverage':.8,'training_rows':int(train.sum()),'calibration_rows':int(cal.sum()),'test_rows':int(test.sum()),'population':'Returning players with at least two prior recorded role-opportunity games; conditional on a role opportunity being recorded. No DNP/zero-opportunity guarantee.'}
        if train.sum()<200 or cal.sum()<100:
            reports.append({**report,'state':'insufficient_data'});continue
        model=make_pipeline(StandardScaler(),Ridge(alpha=100)).fit(X[train],y[train])
        cp=np.maximum(0,model.predict(X[cal]));q=quantile(abs(y[cal]-cp))
        if q is None:reports.append({**report,'state':'insufficient_calibration'});continue
        tp=np.maximum(0,model.predict(X[test])) if test.any() else np.array([])
        lo=np.maximum(0,tp-q);hi=tp+q
        coverage=float(np.mean((y[test]>=lo)&(y[test]<=hi))) if test.any() else None
        # Independent temporal test; width is NOT tuned on this test set.
        report.update({'state':'evaluated' if test.sum()>=100 else 'test_sample_small','residual_quantile':q,'observed_coverage':coverage,'mean_width':float(np.mean(hi-lo)) if test.any() else None,'mae':float(np.mean(abs(y[test]-tp))) if test.any() else None,'trained_through':year-2,'calibration_season':year-1,'test_season':year,'warning':'Temporal dependence and distribution shift mean nominal coverage is not guaranteed. Baseline only; no injury/weather/line/matchup overlays validated.'})
        reports.append(report)
        latest={}
        for _,r in g[g.season.eq(year)].iterrows():latest[r[idcol]]=(r.posteam,r['name'],r.day)
        recent_cutoff=schedule[schedule.season.eq(year)].gameday.max()-pd.Timedelta(days=90)
        for pid,(team,name,day) in latest.items():
            if len(history[pid])<2:continue
            f=feat(history[pid]);pred=max(0,float(model.predict([f])[0]))
            projections.append({'id':pid,'team':team,'name':name,'stat':stat,'prediction':pred,'lower':max(0,pred-q),'upper':pred+q,'target_coverage':.8,'test_coverage':coverage,'test_n':int(test.sum()),'recent_opportunities':f[1],'last_played':str(day.date()),'interval_state':report['state']})
    return projections,reports

"""Sourced context, conservative extraction, explicit unvalidated scenario adjustments."""
import json, re, math
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests

SITE='https://site.api.espn.com/apis/site/v2/sports/football/nfl'
SESSION=requests.Session()
SESSION.headers['User-Agent']='NFL-EDGE-research/2.0'

def get(url,params=None):
    r=SESSION.get(url,params=params,timeout=30);r.raise_for_status();return r.json()
def iso(): return datetime.now(timezone.utc).isoformat()
def dt(s): return datetime.fromisoformat(str(s).replace('Z','+00:00')).astimezone(timezone.utc)
def teamcode(t): return {'WSH':'WAS','LA':'LAR'}.get(t,t)
def local(name,default):
    p=Path('inputs')/name
    return json.loads(p.read_text()) if p.exists() else default

def snap_report(text):
    # Only explicit quantified limits; negations and unquantified statements stay unresolved.
    text=text or ''
    if re.search(r'\b(no|not|without)\b.{0,35}(snap|limit|restrict)',text,re.I):
        return {'kind':'unresolved','reason':'Negation present; manual review required'}
    m=re.search(r'(?:limited to|capped at|snap count of|no more than)\s+(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s*(%|percent|snaps)(?!\w)',text,re.I)
    if m:
        a=int(m.group(1));b=int(m.group(2) or a)
        return {'kind':'reported_numeric','low':min(a,b),'high':max(a,b),'unit':'percent' if m.group(3).lower() in ['%','percent'] else 'snaps','excerpt':m.group(0),'requires_review':True}
    if re.search(r'(snap (?:count|limit)|limited (?:role|snaps)|workload restriction)',text,re.I):
        return {'kind':'reported_unspecified','reason':'Restriction mentioned, no reliable numerical cap'}
    return {'kind':'unknown','reason':'No explicit quantified restriction in supplied report'}

def injuries():
    url=SITE+'/injuries'; stamp=iso()
    try:
        j=get(url);result=[]
        team_lookup={}
        try:
            tj=get(SITE+'/teams',{'limit':100})
            for sport in tj.get('sports',[]):
                for league in sport.get('leagues',[]):
                    for entry in league.get('teams',[]):
                        tm=entry.get('team',{});team_lookup[str(tm.get('id'))]=teamcode(tm.get('abbreviation',''))
        except Exception:
            pass
        for group in j.get('injuries',[]):
            t=group.get('team',{});code=teamcode(t.get('abbreviation','')) or team_lookup.get(str(group.get('id')),'')
            for i in group.get('injuries',[]):
                if not code: continue
                a=i.get('athlete',{});details=i.get('details') or {}
                texts=[i.get('shortComment',''),i.get('longComment',''),details.get('detail','') if isinstance(details,dict) else '']
                report=' '.join(x for x in texts if isinstance(x,str))
                result.append({'espn_id':str(a.get('id','')),'name':a.get('displayName') or a.get('fullName'),'team':code,'position':a.get('position',{}).get('abbreviation'),'status':i.get('status','Unknown'),'report_date':i.get('date'),'report':report,'restriction':snap_report(report),'source_url':url,'retrieved_at':stamp})
        if not result: return {'state':'unavailable','reason':'No parsed injury entries; NOT a healthy roster','rows':[],'retrieved_at':stamp,'source_url':url}
        return {'state':'ok','rows':result,'retrieved_at':stamp,'source_url':url}
    except Exception as e: return {'state':'unavailable','reason':str(e),'rows':[],'retrieved_at':stamp,'source_url':url}

def upcoming_events():
    # Explicit date window prevents relying on ESPN's default definition of "today".
    today=datetime.now(timezone.utc).date()
    url=SITE+'/scoreboard'
    j=get(url,{'dates':f'{today:%Y%m%d}-{today+timedelta(days=14):%Y%m%d}','limit':1000})
    out=[]
    for event in j.get('events',[]):
        c=event.get('competitions',[{}])[0]
        if event.get('status',{}).get('type',{}).get('state')!='pre': continue
        ts={x.get('homeAway'):teamcode(x.get('team',{}).get('abbreviation','')) for x in c.get('competitors',[])}
        out.append({'espn_id':event['id'],'kickoff':event['date'],'home':ts.get('home'),'away':ts.get('away'),'venue':c.get('venue',{}),'source_url':url,'retrieved_at':iso()})
    return out

def weather(event):
    venue=event.get('venue',{});name=venue.get('fullName','')
    catalog=local('venues.json',{})
    config=catalog.get(str(venue.get('id'))) or catalog.get(name)
    result={'state':'unknown','venue':name,'reason':'Venue coordinates/roof not configured','retrieved_at':iso()}
    if not config: return result
    # Exact venue lookup only. Never assume the home team's usual stadium.
    if not config.get('source_url') or not config.get('verified_at'): return {**result,'reason':'Venue requires coordinate provenance'}
    roof=config.get('roof','unknown')
    result.update({'coordinates_source':config['source_url'],'roof':roof})
    if roof=='closed': return {**result,'state':'indoor','reason':'Configured closed roof; no outdoor penalty','pass_multiplier':1.0}
    if roof not in ['open','outdoor']: return {**result,'reason':'Retractable/unknown roof state: outdoor effect not applied'}
    try:
        kickoff=dt(event['kickoff']);url='https://api.open-meteo.com/v1/forecast'
        params={'latitude':config['latitude'],'longitude':config['longitude'],'hourly':'temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m','wind_speed_unit':'mph','timezone':'GMT','timeformat':'unixtime','forecast_days':16}
        j=get(url,params);h=j['hourly'];inds=sorted(range(len(h['time'])),key=lambda k:abs(h['time'][k]-kickoff.timestamp()))[:1]
        k=inds[0]
        if abs(h['time'][k]-kickoff.timestamp())>3600: raise ValueError('Kickoff outside forecast horizon')
        wind=h['wind_speed_10m'][k];rain=h['precipitation'][k];temp=h['temperature_2m'][k];gust=h['wind_gusts_10m'][k]
        if any(v is None for v in [wind,rain,temp,gust]): raise ValueError('Missing weather variable')
        # Scenario sensitivity, not a trained causal weather coefficient.
        penalty=min(.25,max(0,wind-12)*.005+min(rain,8)*.008+max(0,-temp)*.002)
        return {**result,'state':'forecast','source_url':url,'kickoff':event['kickoff'],'forecast_hour':h['time'][k],'wind_mph':wind,'gust_mph':gust,'precip_mm':rain,'temp_c':temp,'pass_multiplier':1-penalty,'effect_type':'heuristic, unvalidated; model forecast, not an observed condition'}
    except Exception as e:return {**result,'reason':str(e)}

def eligible(row,event):
    try:
        return row.get('game_id')==event.get('game_id') and bool(row.get('source_url')) and dt(row['as_of'])<=datetime.now(timezone.utc)<dt(row['expires_at']) and dt(row['as_of'])<dt(event['kickoff'])
    except (KeyError,ValueError,TypeError): return False

def apply_context(game,event,inj,players):
    """Adjust prospective forecasts only. Base validation never claimed for overlays."""
    if not event: return {**game,'context':{'state':'unavailable','reason':'No exact ESPN event/date match'},'scenario_probability':None}
    event={**event,'game_id':game['id']}
    records=[r for r in local('personnel.json',[]) if eligible(r,event)]
    charted=[r for r in local('matchups.json',[]) if eligible(r,event)]
    source_rows=[r for r in inj['rows'] if r['team'] in [game['home'],game['away']]]
    ids=local('player_ids.json',{})
    adj={'home':0.,'away':0.}; notes=[]; effects={}; rejected=[]
    # Roster-specific role and replacement values must be sourced, not guessed by position.
    for r in records:
        if r.get('team') not in [game['home'],game['away']]:continue
        side='home' if r['team']==game['home'] else 'away'
        pid=r.get('player_id'); iid=ids.get(pid)
        injury=next((i for i in source_rows if iid and i['espn_id']==str(iid)),None)
        status=str(injury.get('status','unknown')).lower() if injury else 'unknown'
        # No play probability is inferred from questionable/doubtful.
        availability=0. if status in ['out','injured reserve','ir','suspended'] else r.get('availability')
        if availability is None:
            notes.append(f"{r.get('name',pid)}: {status}; availability unresolved, no automatic injury penalty")
            continue
        availability=float(availability)
        if not 0<=availability<=1: rejected.append('Invalid availability: '+str(pid));continue
        snap=r.get('expected_snap_share');baseline=r.get('baseline_snap_share')
        factor=1.
        if snap is not None and baseline is not None and baseline>0:
            factor=max(0,min(1,float(snap)/float(baseline)))
        lost=1-availability*factor
        impact=float(r.get('replacement_drop_points',0))
        delta=-lost*impact
        adj[side]+=delta;effects[pid]={'availability':availability,'workload_factor':factor,'source_url':r['source_url'],'name':r.get('name',pid)}
        notes.append(f"{r.get('name',pid)} {r.get('position','')}: expected contribution {availability*factor:.0%} of baseline; team scenario {delta:+.2f} points. Replacement drop is a sourced analyst estimate, not a measured causal value.")
    # Explicit opportunity overlap supports line-vs-rusher, receiver-vs-coverage and alignment rows.
    for r in charted:
        if r.get('team') not in [game['home'],game['away']]:continue
        try:
            overlap=float(r['expected_overlap']);opps=float(r['expected_opportunities']);edge=float(r['epa_edge_per_opportunity'])
            if not 0<=overlap<=1 or opps<0 or abs(edge)>1: raise ValueError('invalid matchup range')
            delta=overlap*opps*edge
            side='home' if r['team']==game['home'] else 'away';adj[side]+=delta
            notes.append(f"{r['kind']}: {r['description']}. {opps:g} opportunities × {overlap:.0%} overlap × {edge:+.3f} incremental EPA = {delta:+.2f} scenario points. Must be incremental to team baseline to avoid double counting.")
        except (KeyError,ValueError,TypeError):rejected.append('Invalid matchup row')
    w=weather(event)
    multiplier=w.get('pass_multiplier',1.)
    if multiplier!=1:
        for side in ['home','away']:
            share=game.get(side+'_pass_share',.6)
            # Conservative configured sensitivity, not data-fit effect.
            adj[side]-=(1-multiplier)*share*10
        notes.append('Outdoor weather reduces passing yardage scenarios and team point scenarios; coefficients are unvalidated.')
    delta=max(-14,min(14,adj['home']-adj['away']))
    basep=min(.995,max(.005,game['home_probability']))
    scenario=1/(1+math.exp(-(math.log(basep/(1-basep))+delta/7)))
    projected=[]
    for p in players:
        if p['team'] not in [game['home'],game['away']]:continue
        effect=effects.get(p['id']);f=effect['availability']*effect['workload_factor'] if effect else 1.
        passing=p['stat'] in ['passing_yards','receiving_yards']
        f*=multiplier if passing else 1
        projected.append({**p,'scenario_yards':p['prediction']*f,'scenario_factor':f,'interval_applies_to':'historical baseline, conditional on recorded role opportunity; NOT adjusted scenario','personnel_source':effect})
    return {**game,'scenario_probability':scenario,'scenario_margin':game['margin']+delta,'context':{'state':'partial','event_id':event['espn_id'],'kickoff':event['kickoff'],'injuries_state':inj['state'],'injuries':source_rows,'weather':w,'notes':notes,'rejected':rejected,'point_delta_home':delta,'personnel_rows':len(records),'matchup_rows':len(charted),'missing':['Automatic player identity matches absent unless mapped','No complete live routes/coverage/alignment feed','No automatic numerical snap restriction from vague injury status'],'validation':'Context overlay is NOT covered by base-model historical validation.'},'player_projections':projected}

"""Combine independently covered route markets without manufacturing network totals."""
from __future__ import annotations
from copy import deepcopy
import pandas as pd

LABELS={'anac':'Brasil · ANAC','aerocivil':'Colombia · Aerocivil','caa':'Reino Unido · CAA'}
AICM_LABEL='AICM · vuelos AM programados'
OMA_LABEL='OMA · rutas documentadas'
ESTIMATED_LABEL='AFAC + AeroDataBox · Grupo Aeroméxico estimado'
ESTIMATED_CARRIERS=('AEROMEXICO','AEROMEXICO_CONNECT')
ESTIMATE_TABLE='fact_route_carrier_international_estimate'


def _estimated_routes(estimates, months, endpoint):
    """Grupo Aeroméxico routes estimated from AFAC margins, one per airport market.

    Only a quarter whose every month was fitted is used: a partial quarter
    would read as a full one on the map.
    """
    if estimates.empty or not set(months) <= set(estimates.period_id):
        return {}
    frame=estimates[estimates.period_id.isin(months)]
    routes={}
    for market,group in frame.groupby('market_key'):
        a,b=market.split('<>')
        # Mexico-United States belongs to T-100, which observes it; the map
        # shows that observation (Aerovías only) and is never filled from an
        # estimate, even for a carrier T-100 reports but the map leaves out.
        if 'US' in (endpoint(a)['country'],endpoint(b)['country']):
            continue
        monthly=[]
        for (period,origin,dest),part in group.groupby(['period_id','origin_iata','destination_iata'],sort=True):
            monthly.append(dict(period_id=str(period),carrier_key='AEROMEXICO_GROUP',carrier_label='Grupo Aeroméxico',
                origin_iata=str(origin),destination_iata=str(dest),
                passengers=float(part.passengers_estimated.sum()),
                passengers_low=float(part.passengers_estimated_low.sum()),
                passengers_high=float(part.passengers_estimated_high.sum()),
                seats=None,departures=None,load_factor=None,capacity_estimated=False,
                support_observed_in_period=True,support_source_periods=str(period),support_month_gap=0))
        covered=int(group.period_id.nunique())
        routes[market]=dict(
            market_key=market,origin=endpoint(a),destination=endpoint(b),
            passengers=float(group.passengers_estimated.sum()),
            passengers_low=float(group.passengers_estimated_low.sum()),
            passengers_high=float(group.passengers_estimated_high.sum()),
            passengers_estimated=True,capacity_estimated=False,
            departures_estimated_seed=float(group.departures_estimated.sum()),
            months_covered=covered,months_selected=len(months),monthly=monthly,
            estimator_version=sorted(group.estimator_version.unique())[0])
    return routes

def extend_networks(connection, networks):
    exists=connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='fact_international_route_observations'").fetchone()[0]
    if not exists: return deepcopy(networks)
    frame=connection.execute("SELECT * FROM fact_international_route_observations").df()
    route_frame=frame[(frame.operator_icao=='AMX') & (frame.observation_scope=='carrier_route')].copy()
    aena=frame[(frame.source_system=='aena') & (frame.operator_icao=='AMX') &
               (frame.observation_scope=='carrier_airport')].copy()
    has_aicm=connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='fact_aicm_international_scheduled_route_movements'").fetchone()[0]
    scheduled=connection.execute("SELECT * FROM fact_aicm_international_scheduled_route_movements WHERE observation_status='assigned_slot_not_flown'").df() if has_aicm else pd.DataFrame()
    has_oma=connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='fact_oma_documented_routes'").fetchone()[0]
    oma=connection.execute("SELECT * FROM fact_oma_documented_routes").df() if has_oma else pd.DataFrame()
    has_estimate=connection.execute(f"SELECT count(*) FROM information_schema.tables WHERE table_name='{ESTIMATE_TABLE}'").fetchone()[0]
    estimates=connection.execute(f"SELECT * FROM {ESTIMATE_TABLE} WHERE carrier_key IN {ESTIMATED_CARRIERS}").df() if has_estimate else pd.DataFrame()
    airports=connection.execute('SELECT * FROM dim_airport').df().set_index('airport_iata').to_dict('index')
    def endpoint(code):
        a=airports[code]
        if pd.isna(a['latitude']) or pd.isna(a['longitude']): raise ValueError('Missing coordinates')
        return dict(iata=code,name=a['name'],city=a['city'],country=a['country'],lat=float(a['latitude']),lon=float(a['longitude']))
    def total(group,key):
        if group.empty or group[key].isna().any(): return None
        return float(group[key].sum())
    result=deepcopy(networks)
    for period,network in result.items():
        months=network['expected_months']; original_months=network['observed_months']
        for route in network['routes']:
            route['source_label']='Estados Unidos · BTS T-100'
            route['observed_months']=original_months
            route['coverage_note']='Meses: '+', '.join(m[5:] for m in original_months)+' · BTS T-100'
        route_frame['market_key']=route_frame.apply(lambda r:'<>'.join(sorted([r.origin_iata,r.dest_iata])),axis=1)
        for (source,market),group in route_frame[route_frame.period_id.isin(months)].groupby(['source_system','market_key']):
            if any(r['market_key']==market for r in network['routes']): raise ValueError('Overlapping authority market requires precedence review')
            observed=sorted(group.period_id.unique())
            directions=[]
            for (origin,dest),direction in group.groupby(['origin_iata','dest_iata']):
                directions.append(dict(origin_iata=origin,destination_iata=dest,
                    **{k:total(direction,k) for k in ('passengers','seats','departures')}))
            previous_months=[f'{int(m[:4])-1}{m[4:]}' for m in observed]
            prior=route_frame[(route_frame.source_system==source)&(route_frame.market_key==market)&route_frame.period_id.isin(previous_months)]
            # All directions in each month must be present on both sides for comparable totals.
            directions_set=set(zip(group.origin_iata,group.dest_iata))
            # Isolated one-way observations may be diversions. Keep them in Gold
            # without presenting a bidirectional commercial market on the map.
            if len(directions_set)<2: continue
            def both_directions(g, month):
                return set(zip(g[g.period_id==month].origin_iata,g[g.period_id==month].dest_iata))==directions_set
            complete=len(directions_set)==2 and all(both_directions(group,m) for m in observed)
            comparable=complete and set(prior.period_id)==set(previous_months) and all(both_directions(prior,m) for m in previous_months)
            a,b=market.split('<>')
            network['routes'].append(dict(market_key=market,origin=endpoint(a),destination=endpoint(b),
                **{k:total(group,k) if complete else None for k in ('passengers','seats','departures')},load_factor=None,
                previous={k:total(prior,k) if comparable else None for k in ('passengers','seats','departures')},
                directions=directions,source_label=LABELS[source],observed_months=observed,
                coverage_note='Meses: '+', '.join(m[5:] for m in observed)+' · '+LABELS[source]+(' · falta un sentido' if not complete else ''),
                source_hashes=sorted(group.source_hash.unique()),record_ids=sorted(group.record_id.unique()),
                operation_status='operated_observed',carrier_role='operator_reporting_carrier',marketing_carrier=None,agent_eligible=False))
        # Add scheduled AICM markets missing from the observed network. If a
        # market is already observed, keep its measured metrics and attach the
        # full-quarter schedule separately; never sum the two populations.
        if not scheduled.empty:
            current_slots=scheduled[scheduled.period_id.isin(months)].copy()
            if not current_slots.empty:
                current_slots['market_key']=current_slots.apply(
                    lambda r:'<>'.join(sorted((r.origin_iata,r.dest_iata))),axis=1)
                for market,group in current_slots.groupby('market_key'):
                    scheduled_count=int(group.scheduled_movements.sum())
                    matching=next((r for r in network['routes'] if r['market_key']==market),None)
                    if matching is not None:
                        matching['scheduled_movements_q2']=scheduled_count
                        matching['scheduled_source_label']=AICM_LABEL
                        matching['coverage_note']+=f' · AICM abr–jun: {scheduled_count:,} programados'
                        continue
                    a,b=market.split('<>')
                    directions=[dict(origin_iata=origin,destination_iata=dest,
                        passengers=None,seats=None,departures=int(part.scheduled_movements.sum()))
                        for (origin,dest),part in group.groupby(['origin_iata','dest_iata'])]
                    network['routes'].append(dict(
                        market_key=market,origin=endpoint(a),destination=endpoint(b),
                        passengers=None,seats=None,departures=scheduled_count,load_factor=None,
                        previous={k:None for k in ('passengers','seats','departures')},
                        directions=directions,source_label=AICM_LABEL,
                        observed_months=[],scheduled_months=sorted(group.period_id.unique()),
                        coverage_note='Abr–jun 2026 · AICM · programado, ejecución sin verificar',
                        source_hashes=sorted(group.source_hash.unique()),
                        record_ids=sorted(group.record_id.unique()),
                        operation_status='assigned_slot_not_flown',
                        carrier_role='AM_flight_number_slot_holder',
                        marketing_carrier=None,agent_eligible=False))
        if not oma.empty:
            quarter_routes=oma[oma.period_id.eq(period)].copy()
            if not quarter_routes.empty:
                quarter_routes['market_key']=quarter_routes.apply(
                    lambda r:'<>'.join(sorted((r.origin_iata,r.dest_iata))),axis=1)
                for market,group in quarter_routes.groupby('market_key'):
                    if any(r['market_key']==market for r in network['routes']):
                        raise ValueError('OMA market overlaps an existing route; review precedence')
                    a,b=market.split('<>')
                    directions=[dict(origin_iata=row.origin_iata,destination_iata=row.dest_iata,
                                     passengers=None,seats=None,
                                     departures=int(row.scheduled_movements) if pd.notna(row.scheduled_movements) else None)
                                for row in group.itertuples(index=False)]
                    count=int(group.scheduled_movements.sum()) if group.scheduled_movements.notna().all() else None
                    status='scheduled_from_dated_release' if count is not None else 'documented_operating_route_count_unavailable'
                    network['routes'].append(dict(
                        market_key=market,origin=endpoint(a),destination=endpoint(b),
                        passengers=None,seats=None,departures=count,load_factor=None,
                        previous={k:None for k in ('passengers','seats','departures')},
                        directions=directions,source_label=OMA_LABEL,
                        observed_months=[],scheduled_months=months if count is not None else [months[0]],
                        coverage_note=(f'Abr–jun 2026 · OMA · {count} programados' if count is not None
                                       else 'OMA 13 abr 2026 · ruta operada; incluida en Madrid Aena, sin desglose por origen'),
                        source_hashes=sorted(group.source_hash.unique()),
                        record_ids=sorted(group.record_id.unique()),
                        operation_status=status,carrier_role='airline_named_in_airport_release',
                        marketing_carrier=None,agent_eligible=False))
        # Estimated passengers fill only what no source measured. An observed
        # market keeps its observation; a market with flights but no
        # passengers gains the estimate beside its own flights; a market no
        # source quantified is added, labelled as an estimate throughout.
        for market,estimate in _estimated_routes(estimates,months,endpoint).items():
            matching=next((r for r in network['routes'] if r['market_key']==market),None)
            months_text=', '.join(sorted({m['period_id'][5:] for m in estimate['monthly']}))
            note=f"Pasajeros estimados de Grupo Aeroméxico (AFAC + AeroDataBox) · meses {months_text}"
            if matching is not None and matching.get('passengers') is not None:
                continue
            payload={k:estimate[k] for k in ('passengers','passengers_low','passengers_high','passengers_estimated',
                'capacity_estimated','months_covered','months_selected','monthly','estimator_version')}
            if matching is not None:
                # The estimate covers only the months the route's own source
                # covers, so passengers and flights describe the same window
                # (CAA reports June alone; a quarter of passengers beside a
                # month of flights would read as a load factor it is not).
                own_months=set(matching.get('observed_months') or matching.get('scheduled_months') or months)
                monthly=[item for item in estimate['monthly'] if item['period_id'] in own_months]
                if not monthly:
                    continue
                payload['monthly']=monthly
                payload['months_covered']=len({item['period_id'] for item in monthly})
                # Each measured direction takes its own estimate, so the
                # directions still add up to the route they belong to.
                by_direction={}
                for item in monthly:
                    key=(item['origin_iata'],item['destination_iata'])
                    sums=by_direction.setdefault(key,dict(passengers=0.0,passengers_low=0.0,passengers_high=0.0))
                    for metric in sums: sums[metric]+=item[metric]
                for direction in matching['directions']:
                    direction.update(by_direction.get((direction['origin_iata'],direction['destination_iata']),
                                                      dict(passengers=0.0,passengers_low=0.0,passengers_high=0.0)))
                matching.update(payload)
                for metric in ('passengers','passengers_low','passengers_high'):
                    matching[metric]=float(sum(d[metric] for d in matching['directions']))
                matching['coverage_note']+=' · Pasajeros estimados de Grupo Aeroméxico (AFAC + AeroDataBox) · meses '+', '.join(sorted({m['period_id'][5:] for m in monthly}))
                continue
            network['routes'].append(dict(
                market_key=market,origin=estimate['origin'],destination=estimate['destination'],
                **payload,seats=None,departures=round(estimate['departures_estimated_seed']),load_factor=None,
                previous={k:None for k in ('passengers','seats','departures')},
                directions=[],source_label=ESTIMATED_LABEL,
                observed_months=[],estimated_months=sorted({m['period_id'] for m in estimate['monthly']}),
                coverage_note=note+' · vuelos: frecuencias de AeroDataBox',
                operation_status='estimated_from_afac_margins_and_aerodatabox_seed',
                carrier_role='operating_carrier_estimated',marketing_carrier=None,agent_eligible=False))
        # Aena's company exports identify an airport, not the Mexican endpoint.
        # Present them alongside the map, never as a carrier-route observation.
        activity=[]
        current=aena[aena.period_id.isin(months)]
        for airport,group in current.groupby('airport_iata'):
            if airport not in ('MAD','BCN'): continue
            values={}
            coverage={}
            for metric in ('passengers','operations'):
                metric_rows=group[group.metric_key==metric]
                if metric_rows.duplicated(['period_id']).any():
                    raise ValueError('Duplicate Aena company-airport month')
                coverage[metric]=sorted(metric_rows.period_id.unique())
            shared=sorted(set(coverage['passengers']) & set(coverage['operations']))
            if not shared: continue
            for metric in ('passengers','operations'):
                values[metric]=total(group[(group.metric_key==metric) & group.period_id.isin(shared)],metric)
            activity.append(dict(airport_iata=airport,airport_name=endpoint(airport)['name'],
                                 passengers=values['passengers'],operations=values['operations'],
                                 observed_months=shared,
                                 expected_months=months,source_label='España · Aena',
                                 coverage_status='complete' if set(shared)==set(months) else 'partial'))
        network['aena_airport_activity']=activity
        aps={e['iata']:e for r in network['routes'] for e in (r['origin'],r['destination'])}
        network['airports']=sorted(aps.values(),key=lambda a:a['iata'])
        network['route_count']=len(network['routes']);network['airport_count']=len(aps)
        network['coverage']='Mercados observados y programados por fuente; cobertura parcial de la red internacional'
        network['coverage_by_source']={label:sorted({m for r in network['routes'] if r.get('source_label')==label for m in (r.get('observed_months') or r.get('scheduled_months') or r.get('estimated_months',[]))}) for label in sorted({r['source_label'] for r in network['routes']})}
        network['estimated_passenger_route_count']=sum(bool(r.get('passengers_estimated')) for r in network['routes'])
        # Different source windows and metric populations cannot form a worldwide total.
        network['totals']={k:None for k in ('passengers','seats','departures')}
        network['agent_eligible']=False
    return result

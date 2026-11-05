#!/usr/bin/env python3
"""Transparent sizing and cost model for the three-site IDP architecture proposal.

Every number is a planning assumption or a modelled estimate - not a vendor benchmark,
storage quote or price. Coefficients cite their source in the comments; everything
else is an explicit assumption listed in docs/01-scope-and-assumptions.md.

    python tools/capacity_model.py               # telemetry volumes (unchanged contract)
    python tools/capacity_model.py --assumptions # volumes + assumptions
    python tools/capacity_model.py --full        # + per-site compute/storage, fleet, TCO, programme cost
"""
from dataclasses import dataclass, asdict, field
import argparse, json, math

GIB = 2**30; TIB = 2**40; GB = 10**9; TB = 10**12


@dataclass(frozen=True)
class Assumptions:
    clusters: int = 30
    pods: int = 1500
    series_per_pod: int = 250
    series_per_cluster: int = 10000
    series_headroom: float = 1.5
    scrape_seconds: int = 15
    metric_bytes_per_sample: float = 2.5
    metric_object_overhead: float = 1.5
    provision_headroom: float = 1.5
    raw_metric_days: int = 30
    capacity_series: int = 40000
    capacity_scrape_seconds: int = 300
    capacity_days: int = 395
    capacity_bytes_per_sample: float = 3
    capacity_object_overhead: float = 2
    logs_gib_per_pod_day: float = .28
    logs_platform_gib_day: float = 80
    logs_compressed_ratio: float = .35
    loki_storage_overhead: float = 1.3
    logs_days: int = 30
    audit_gib_day: float = 20
    audit_days: int = 400
    traces_before_sampling_spans_s: int = 10000
    traces_sampling_fraction: float = .10
    trace_bytes_per_span: int = 700
    traces_days: int = 7


def calculate(a: Assumptions):
    """Fleet-wide telemetry volumes (the figures quoted in docs/06 and the NFR note)."""
    active = (a.pods*a.series_per_pod + a.clusters*a.series_per_cluster)*a.series_headroom
    rate = active/a.scrape_seconds
    metric_day_bytes = rate*86400*a.metric_bytes_per_sample*a.metric_object_overhead
    metric_tier = metric_day_bytes*a.raw_metric_days*a.provision_headroom
    cap_rate = a.capacity_series/a.capacity_scrape_seconds
    cap_bytes = cap_rate*86400*a.capacity_days*a.capacity_bytes_per_sample*a.capacity_object_overhead*a.provision_headroom
    logs_raw_gib = a.pods*a.logs_gib_per_pod_day+a.logs_platform_gib_day
    loki_logical_bytes = logs_raw_gib*GIB*a.logs_compressed_ratio*a.loki_storage_overhead*a.logs_days*a.provision_headroom
    audit_logical_bytes = a.audit_gib_day*GIB*a.logs_compressed_ratio*a.audit_days*a.provision_headroom
    trace_rate = a.traces_before_sampling_spans_s*a.traces_sampling_fraction
    trace_logical_bytes = trace_rate*86400*a.trace_bytes_per_span*a.traces_days*a.provision_headroom
    return {
      'active_series': round(active), 'samples_per_second': round(rate),
      'metric_raw_30d_logical_tb': round(metric_tier/GB/1000, 3),
      'metric_capacity_13mo_logical_gb': round(cap_bytes/GB, 2),
      'logs_uncompressed_gib_per_day': round(logs_raw_gib, 1),
      'loki_30d_provisioned_tib': round(loki_logical_bytes/TIB, 2),
      'north_audit_400d_provisioned_tib': round(audit_logical_bytes/TIB, 2),
      'tempo_7d_provisioned_tb': round(trace_logical_bytes/(1000*GB), 2),
      'trace_retained_spans_per_second': round(trace_rate),
      'pilot_burst_target_samples_per_second': round(rate*3)
    }


# --------------------------------------------------------------------------- sizing
@dataclass(frozen=True)
class SizingAssumptions:
    # Site shares are DERIVED from the topology (A-01/A-02/A-12), not assumed: Central hosts 12 clusters and the
    # production pods; South hosts 18 clusters (its 10 DR clusters idle) and the non-production pods.
    central_clusters: int = 12
    # Mimir write path - "Planning Grafana Mimir capacity" (grafana.com, checked 2026-11-05):
    # distributor 1 core + 1 GB per 25k samples/s; ingester 1 core + 2.5 GB + 5 GB disk per 300k in-memory series.
    # Grafana calls these rough; its runbooks cite ~2M series per ingester, so this is a conservative upper bound.
    mimir_rf: int = 3
    distributor_samples_per_core: int = 25000
    ingester_series_per_unit: int = 300000
    # Fixed per-site components (assumptions; read path depends on query load, not ingest):
    # (vCPU, GiB) per component group
    mimir_read_and_maintenance: tuple = (12.75, 35.5)   # queriers, frontends, store-gateways, compactor, ruler, alertmanager
    # Loki "Size the cluster" smallest tier (p90, grafana.com, checked 2026-11-05): 6 ingesters 2 CPU/4 Gi,
    # 10 queriers 1 CPU/1 Gi, compactor 2 CPU/10 Gi; distributors and frontends assumed 1 CPU/1 Gi each.
    loki_smallest_tier: tuple = (30.0, 50.0)
    tempo: tuple = (8.0, 16.0)                 # assumption at ~1,000 retained spans/s fleet-wide
    grafana: tuple = (2.0, 4.0)
    gateways: tuple = (4.0, 4.0)               # write + read gateways, HA
    memcached: tuple = (3.0, 24.0)
    metamonitoring: tuple = (1.0, 4.0)
    audit_relay: tuple = (1.5, 3.0)
    ha_node_loss_headroom: float = 1.25        # spare capacity to survive one node loss per site
    # Broker (Kafka-compatible, Data Engineering): assumptions
    broker_nodes: int = 3
    broker_node: tuple = (4.0, 16.0)
    broker_bytes_per_sample: float = 10.0      # A-15: remote-write payload on the broker, conservative
    broker_retention_hours: int = 24
    broker_rf: int = 3
    # Fleet overhead (assumptions)
    control_plane_vms: int = 3
    control_plane_vm: tuple = (4.0, 16.0)
    collectors_per_cluster: tuple = (1.0, 2.0)
    management_workloads_per_site: tuple = (16.0, 64.0)   # CAPI/CAPV, Flux, Backstage, runners, OpenTofu
    south_enabling_services: tuple = (48.0, 192.0)       # IdP, CA, secret manager, DNS, registry, vCenter appliances (ADR 0011)
    # Workload capacity (A-12): only the *incremental* DR reserve and South non-prod are programme costs;
    # Central production capacity already exists today on the legacy clusters.
    production_pods: int = 900
    prod_pod_request: tuple = (0.5, 1.0)
    dr_reserve_headroom: float = 1.2
    nonprod_pods: int = 600
    nonprod_pod_request: tuple = (0.25, 0.5)
    production_data_tib: float = 20.0          # A-12: production data to replicate to South and back up to North
    backup_generations_factor: float = 2.0     # North keeps ~2x the data volume across retained generations
    # GitLab and registries (A-18): HA increment of the Central primary + South Geo secondary; South OCI registry
    gitlab_ha_and_geo: tuple = (48.0, 192.0)
    gitlab_geo_copy_tib: float = 10.0
    south_registry_tib: float = 5.0
    local_volumes_tib_per_site: float = 0.5    # ingester/store-gateway disks, collector WAL, audit spool
    # Migration (A-19): legacy and new Central capacity run in parallel for ~25% of production for one year
    migration_overlap_fraction: float = 0.25
    migration_overlap_years: float = 1.0
    burst_factor: float = 3.0                  # NFR: 3x ingest burst
    physical_factors: tuple = (1.5, 2.0, 3.0)  # erasure coding / replication scenarios (not vendor figures)


def _add(*parts):
    return (round(sum(p[0] for p in parts), 2), round(sum(p[1] for p in parts), 2))


def site_shares(a: Assumptions, s: SizingAssumptions):
    """Central share of each signal, derived from where clusters and pods actually run."""
    central_pods = s.production_pods
    assert central_pods + s.nonprod_pods == a.pods, 'production + non-production pods must equal the fleet total'
    metrics = (central_pods*a.series_per_pod + s.central_clusters*a.series_per_cluster) / \
              (a.pods*a.series_per_pod + a.clusters*a.series_per_cluster)
    logs = (central_pods*a.logs_gib_per_pod_day + a.logs_platform_gib_day*s.central_clusters/a.clusters) / \
           (a.pods*a.logs_gib_per_pod_day + a.logs_platform_gib_day)
    traces = central_pods/a.pods
    return {'metrics': round(metrics, 4), 'logs': round(logs, 4), 'traces': round(traces, 4)}


def site_sizing(a: Assumptions, s: SizingAssumptions):
    v = calculate(a)
    series, rate = v['active_series'], v['samples_per_second']
    sh = site_shares(a, s)

    def lgtm(share):
        dist = rate*share/s.distributor_samples_per_core
        ing = series*share*s.mimir_rf/s.ingester_series_per_unit
        mimir_write = (round(dist+ing, 2), round(dist*1.0*GB/GIB + ing*2.5*GB/GIB, 2))
        total = _add(mimir_write, s.mimir_read_and_maintenance, s.loki_smallest_tier, s.tempo, s.grafana,
                     s.gateways, s.memcached, s.metamonitoring, s.audit_relay)
        with_ha = (round(total[0]*s.ha_node_loss_headroom, 1), round(total[1]*s.ha_node_loss_headroom, 1))
        return {'mimir_distributor_cores': round(dist, 2), 'mimir_ingester_cores': round(ing, 2),
                'mimir_ingester_ram_gb': round(ing*2.5, 1), 'mimir_ingester_disk_gb': round(ing*5, 1),
                'burst_3x_distributor_cores': round(dist*s.burst_factor, 2),
                'lgtm_vcpu_gib': total, 'lgtm_with_ha_headroom_vcpu_gib': with_ha}

    def broker(m_share, t_share):
        metric_bps = rate*m_share*s.broker_bytes_per_sample
        trace_bps = v['trace_retained_spans_per_second']*t_share*a.trace_bytes_per_span
        disk = (metric_bps+trace_bps)*3600*s.broker_retention_hours*s.broker_rf
        return {'write_mb_per_s': round((metric_bps+trace_bps)/1e6, 2),
                'burst_3x_write_mb_per_s': round((metric_bps+trace_bps)*s.burst_factor/1e6, 2),
                'disk_total_gb_incl_rf': round(disk/GB, 0),
                'disk_per_broker_gb_2x_headroom': round(disk/GB/s.broker_nodes*2, 0),
                'nodes_vcpu_gib': (s.broker_nodes*s.broker_node[0], s.broker_nodes*s.broker_node[1])}

    tib = lambda x_tb: x_tb*TB/TIB
    mimir_tib = tib(v['metric_raw_30d_logical_tb']); cap_tib = v['metric_capacity_13mo_logical_gb']*GB/TIB
    loki_tib = v['loki_30d_provisioned_tib']; tempo_tib = tib(v['tempo_7d_provisioned_tb'])
    audit_tib = v['north_audit_400d_provisioned_tib']
    op_total = mimir_tib+cap_tib+loki_tib+tempo_tib
    m, l, t = sh['metrics'], sh['logs'], sh['traces']
    central_op = (mimir_tib+cap_tib)*m + loki_tib*l + tempo_tib*t
    storage = {
        'central_logical_tib': round(central_op, 2),
        'south_normal_logical_tib': round(op_total - central_op + audit_tib + cap_tib*m, 2),
        'south_after_failover_upper_bound_tib': round(op_total + audit_tib + cap_tib*m, 2),
        'north_audit_logical_tib': round(audit_tib, 2),
        'note': 'South includes the second audit copy (ADR 0010) and the Central capacity copy; after failover, 30 days of recovered telemetry is the upper bound, it grows from zero.',
    }
    phys = {f'x{f}': {k: round(storage[k]*f, 1) for k in storage if k.endswith('_tib')} for f in s.physical_factors}
    return {'shares_central': sh,
            'central': {**lgtm(m), 'broker': broker(m, t)},
            'south_normal': {**lgtm(1-m), 'broker': broker(1-m, 1-t)},
            'south_after_failover': {**lgtm(1.0), 'broker': broker(1.0, 1.0)},
            'storage_logical': storage, 'storage_physical_scenarios': phys}


def fleet(a: Assumptions, s: SizingAssumptions):
    cp = (a.clusters*s.control_plane_vms*s.control_plane_vm[0], a.clusters*s.control_plane_vms*s.control_plane_vm[1])
    col = (a.clusters*s.collectors_per_cluster[0], a.clusters*s.collectors_per_cluster[1])
    mgmt = (2*s.management_workloads_per_site[0], 2*s.management_workloads_per_site[1])
    reserve = (round(s.production_pods*s.prod_pod_request[0]*s.dr_reserve_headroom, 1),
               round(s.production_pods*s.prod_pod_request[1]*s.dr_reserve_headroom, 1))
    nonprod = (s.nonprod_pods*s.nonprod_pod_request[0], s.nonprod_pods*s.nonprod_pod_request[1])
    cp_one = (s.control_plane_vms*s.control_plane_vm[0], s.control_plane_vms*s.control_plane_vm[1])
    dr_cp = (10*cp_one[0], 10*cp_one[1])
    prod_requests = (s.production_pods*s.prod_pod_request[0], s.production_pods*s.prod_pod_request[1])
    return {'control_planes_30_clusters_vcpu_gib': cp, 'of_which_10_dr_control_planes': dr_cp,
            # Variant B (tiered): 1:1 for the 5 most critical clusters + 2 shared DR clusters for the other 5 -> 3 fewer control planes.
            'tiered_dr_variant_saving_vcpu_gib': (3*cp_one[0], 3*cp_one[1]),
            # Variant C (pooled): 3 shared DR clusters for all 10 production clusters -> 7 fewer control planes.
            'pooled_dr_variant_saving_vcpu_gib': (7*cp_one[0], 7*cp_one[1]),
            'cluster_collectors_vcpu_gib': col, 'management_workloads_vcpu_gib': mgmt,
            'south_enabling_services_vcpu_gib': s.south_enabling_services,
            'gitlab_ha_increment_and_geo_secondary_vcpu_gib': s.gitlab_ha_and_geo,
            'south_dr_reserve_vcpu_gib': reserve, 'south_nonprod_vcpu_gib': nonprod,
            'migration_overlap_vcpu_years': round(prod_requests[0]*s.migration_overlap_fraction*s.migration_overlap_years, 1)}


# --------------------------------------------------------------------------- costs (illustrative)
@dataclass(frozen=True)
class CostScenario:
    """Illustrative unit costs - NOT quotations. Replace with client rates and vendor proposals."""
    name: str
    eur_per_vcpu_year: float     # incl. ~4 GiB RAM share, hardware amortisation, hypervisor licence, power/space
    eur_per_tib_year: float      # usable on-prem object/block storage incl. protection overhead
    subscriptions_eur_year: float  # appliances/support beyond OSS (HSM, backup software, optional Grafana/RHDH/broker support)
    run_fte_by_team: tuple       # incremental client run effort once fully live: (SRE, Platform Eng., Data Eng., Network Sec.)
    kiratech_person_months: float
    eur_per_fte_year: float = 110_000   # one blended loaded rate for all people (client and Kiratech); NOT a Kiratech price
    run_years_equivalent: float = 2.5   # ramp: 50% in year 1, 100% in years 2-3
    physical_factor: float = 2.0

    @property
    def client_run_fte(self):
        return round(sum(self.run_fte_by_team), 2)


SCENARIOS = {
    # run_fte_by_team: SRE includes the observability OSS effort of docs/10 section 3 (2.1 FTE in base)
    'low': CostScenario('low', 200, 150, 0, (1.5, 1.5, 0.6, 0.4), 60),
    'base': CostScenario('base', 350, 300, 70_000, (2.1, 2.0, 0.8, 0.6), 80),
    'high': CostScenario('high', 600, 600, 270_000, (3.0, 2.6, 1.1, 0.8), 110),
}


def programme_cost(a: Assumptions, s: SizingAssumptions, c: CostScenario, years: int = 3):
    sz = site_sizing(a, s); fl = fleet(a, s)
    vcpu = {
        'lgtm_central': sz['central']['lgtm_with_ha_headroom_vcpu_gib'][0],
        'lgtm_south_sized_for_failover': sz['south_after_failover']['lgtm_with_ha_headroom_vcpu_gib'][0],
        'brokers_both_sites': 2*sz['central']['broker']['nodes_vcpu_gib'][0],
        'control_planes': fl['control_planes_30_clusters_vcpu_gib'][0],
        'collectors': fl['cluster_collectors_vcpu_gib'][0],
        'management_workloads': fl['management_workloads_vcpu_gib'][0],
        'south_enabling_services': fl['south_enabling_services_vcpu_gib'][0],
        'gitlab_ha_increment_and_geo_secondary': fl['gitlab_ha_increment_and_geo_secondary_vcpu_gib'][0],
        'south_dr_reserve': fl['south_dr_reserve_vcpu_gib'][0],
        'south_nonprod': fl['south_nonprod_vcpu_gib'][0],
    }
    st = sz['storage_logical']
    broker_tib = (sz['central']['broker']['disk_total_gb_incl_rf'] + sz['south_after_failover']['broker']['disk_total_gb_incl_rf'])*GB/TIB
    tib_logical = {
        'lgtm_central': st['central_logical_tib'],
        'south_incl_audit_copy_failover_bound': st['south_after_failover_upper_bound_tib'],
        'north_audit': st['north_audit_logical_tib'],
        'broker_and_local_volumes': broker_tib + 2*s.local_volumes_tib_per_site,
        'gitlab_geo_copy': s.gitlab_geo_copy_tib,
        'south_registry': s.south_registry_tib,
        'production_data_south_replica': s.production_data_tib,
        'production_backups_north': s.production_data_tib*s.backup_generations_factor,
    }
    vcpu_total = sum(vcpu.values()); tib_physical = sum(tib_logical.values())*c.physical_factor
    infra_compute = vcpu_total*c.eur_per_vcpu_year*years
    migration_overlap = fl['migration_overlap_vcpu_years']*c.eur_per_vcpu_year
    infra_storage = tib_physical*c.eur_per_tib_year*years
    subscriptions = c.subscriptions_eur_year*years
    client_people = c.client_run_fte*c.eur_per_fte_year*c.run_years_equivalent
    kiratech = c.kiratech_person_months*c.eur_per_fte_year/12
    total = infra_compute+migration_overlap+infra_storage+subscriptions+client_people+kiratech
    r = lambda x: round(x/1000)  # kEUR
    return {'scenario': c.name, 'vcpu_by_item': {k: round(v, 1) for k, v in vcpu.items()}, 'vcpu_total': round(vcpu_total),
            'storage_logical_tib_by_item': {k: round(v, 2) for k, v in tib_logical.items()}, 'storage_physical_tib': round(tib_physical, 1),
            'client_run_fte': c.client_run_fte, 'run_fte_by_team_sre_pe_de_ns': c.run_fte_by_team,
            'keur_3y': {'infrastructure_compute': r(infra_compute), 'migration_overlap_one_off': r(migration_overlap),
                        'infrastructure_storage': r(infra_storage),
                        'subscriptions_appliances': r(subscriptions), 'client_people_run': r(client_people),
                        'kiratech_engagement': r(kiratech), 'total': r(total)},
            'largest_compute_items': sorted(vcpu, key=vcpu.get, reverse=True)[:3]}


def observability_tco(a: Assumptions, s: SizingAssumptions, c: CostScenario, years: int = 3,
                      oss_fte: float = 2.1, supported_fte: float = 1.5, subscription_eur_year: float = 150_000):
    """3-year observability TCO, OSS vs supported. FTE by activity in docs/10; subscription is a placeholder."""
    sz = site_sizing(a, s)
    vcpu = (sz['central']['lgtm_with_ha_headroom_vcpu_gib'][0] + sz['south_after_failover']['lgtm_with_ha_headroom_vcpu_gib'][0]
            + 2*sz['central']['broker']['nodes_vcpu_gib'][0])
    st = sz['storage_logical']
    broker_tib = (sz['central']['broker']['disk_total_gb_incl_rf'] + sz['south_after_failover']['broker']['disk_total_gb_incl_rf'])*GB/TIB
    tib = (st['central_logical_tib'] + st['south_after_failover_upper_bound_tib'] + st['north_audit_logical_tib']
           + broker_tib + 2*s.local_volumes_tib_per_site)*c.physical_factor
    infra = vcpu*c.eur_per_vcpu_year*years + tib*c.eur_per_tib_year*years
    oss = infra + oss_fte*years*c.eur_per_fte_year
    sup = infra + supported_fte*years*c.eur_per_fte_year + subscription_eur_year*years
    return {'scenario': c.name, 'infra_keur': round(infra/1000), 'oss_keur': round(oss/1000), 'supported_keur': round(sup/1000),
            'difference_keur': round((sup-oss)/1000), 'break_even_subscription_keur_year': round((oss_fte-supported_fte)*c.eur_per_fte_year/1000),
            'fte_sensitivity_oss_keur': {f: round((infra + f*years*c.eur_per_fte_year)/1000) for f in (1.5, 2.1, 2.5, 3.0)}}


# --------------------------------------------------------------------------- DR critical path (modelled, docs/05 section 7)
DR_STEPS = {  # minutes; modelling assumptions until per-step measurements exist
    'detect': 15, 'declare_and_fence': 20,
    'enabling_services_verify': 15, 'geo_promotion_off_path': 45, 'data_promotion': 60, 'worker_scale_out': 40,
    'activate': 30, 'validate': 25, 'traffic_switch': 10, 'signoff': 15,
}
BASELINE_SEQUENTIAL = (15, 20, 40, 90, 50, 25)


def dr_path(steps=None, geo_on_path=False, restore_tib=0.0, link_gbps=1.0, efficiency=0.7):
    d = dict(DR_STEPS, **(steps or {}))
    parallel = [d['enabling_services_verify'], d['data_promotion'], d['worker_scale_out']]
    if geo_on_path: parallel.append(d['geo_promotion_off_path'])
    if restore_tib: parallel.append(transfer_hours(restore_tib, link_gbps, efficiency)*60)
    return round(d['detect'] + d['declare_and_fence'] + max(parallel) + d['activate'] + d['validate'] + d['traffic_switch'] + d['signoff'])


def transfer_hours(tib, link_gbps, efficiency=0.7):
    return tib*TIB*8/(link_gbps*1e9*efficiency)/3600


def dr_summary():
    t = dr_path()
    return {'baseline_sequential_min': sum(BASELINE_SEQUENTIAL), 'designed_min': t, 'slack_min': 240-t,
            'slack_pct': round((240-t)/240*100, 1),
            'sensitivity_min': {'db_90': dr_path({'data_promotion': 90}), 'declaration_60': dr_path({'declare_and_fence': 45}),
                                'activation_60': dr_path({'activate': 60}), 'workers_70': dr_path({'worker_scale_out': 70}),
                                'geo_90_on_path': dr_path({'geo_promotion_off_path': 90}, geo_on_path=True),
                                'db_90_and_declaration_60': dr_path({'data_promotion': 90, 'declare_and_fence': 45}),
                                'restore_1tib_at_1gbps': dr_path(restore_tib=1.0)},
            # Wait at most 60 min for a credible Central restore before declaring: detection 15 + wait 60 + rest of path.
            'declare_after_60min_wait_min': t + 60,
            'transfer_1tib_hours': {'0.1gbps': round(transfer_hours(1, 0.1), 2), '1gbps': round(transfer_hours(1, 1), 2),
                                    '10gbps': round(transfer_hours(1, 10), 2)}}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pods', type=int, default=1500)
    p.add_argument('--clusters', type=int, default=30)
    p.add_argument('--assumptions', action='store_true')
    p.add_argument('--full', action='store_true')
    o = p.parse_args()
    a = Assumptions(pods=o.pods, clusters=o.clusters); s = SizingAssumptions()
    if o.full:
        out = {'estimate': calculate(a), 'sites': site_sizing(a, s), 'fleet': fleet(a, s), 'dr_critical_path': dr_summary(),
               'observability_tco': {k: observability_tco(a, s, c) for k, c in SCENARIOS.items()},
               'programme_cost': {k: programme_cost(a, s, c) for k, c in SCENARIOS.items()}}
        if o.assumptions:
            out['assumptions'] = {'telemetry': asdict(a), 'sizing': asdict(s), 'cost_scenarios': {k: asdict(c) for k, c in SCENARIOS.items()}}
    else:
        out = {'assumptions': asdict(a), 'estimate': calculate(a)} if o.assumptions else calculate(a)
    print(json.dumps(out, indent=2))

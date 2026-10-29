"""Measured-input estimates; never invent throughput or prices."""
def estimate(plan, measurements):
    result = {'planned_episodes':plan['job_count'], 'status':'insufficient measurements',
              'serial_episode_seconds':None,'elapsed_seconds':None,'gpu_allocation_hours':None,
              'gatekeeper_cpu_seconds':None,'api_charge':None}
    durations = measurements.get('mean_episode_seconds', {})
    keys = [j['actor_profile']+'/'+j['mode'] for j in plan['jobs']]
    if all(k in durations for k in keys):
        result['serial_episode_seconds'] = sum(durations[k] for k in keys)
        result['status'] = 'measured pilot estimate'
    throughput = measurements.get('episodes_per_second')
    if throughput and measurements.get('measured_concurrency'):
        result['elapsed_seconds'] = len(keys)/throughput
        result['throughput_measurement_concurrency'] = measurements['measured_concurrency']
    if 'gpu_count' in measurements and 'allocation_seconds' in measurements:
        result['gpu_allocation_hours'] = measurements['gpu_count']*measurements['allocation_seconds']/3600
    result['gatekeeper_cpu_seconds'] = measurements.get('gatekeeper_cpu_seconds')
    if all(k in measurements for k in ('input_tokens','output_tokens','input_price_per_million','output_price_per_million')):
        result['api_charge'] = (measurements['input_tokens']*measurements['input_price_per_million']+measurements['output_tokens']*measurements['output_price_per_million'])/1e6
    return result

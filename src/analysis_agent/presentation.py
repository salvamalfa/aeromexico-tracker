"""Finite, unit-checked formats preserving the reviewed Spanish quarterly text."""

def reviewed_value(node, mode):
    value, unit = node['value'], node['unit']
    if mode in ('usd_millions_0', 'usd_millions_1') and unit == 'USD':
        digits = int(mode[-1])
        return f'US${value / 1e6:,.{digits}f} millones'
    if mode == 'decline_percent' and unit == 'percent_change' and value <= 0:
        return f'{abs(value):.1f}%'
    if mode == 'integer_percent' and unit == 'fraction':
        return f'{value * 100:.0f}%'
    if mode == 'multiple_number' and unit == 'multiple':
        return f'{value:.1f}'
    if mode == 'native_cents_number' and unit == 'cents_USD_per_ASM':
        return f'{value:.1f}'
    if mode == 'period_year' and len(node['period_id']) == 6 and node['period_id'][4] == 'Q':
        return node['period_id'][:4]
    if mode == 'previous_period_label' and node['period_id'] == '2026Q3':
        return '2T26'
    raise ValueError('Incompatible reviewed presentation unit or value')

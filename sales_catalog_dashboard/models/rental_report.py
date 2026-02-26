# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from collections import defaultdict


class SaleRentalReport(models.Model):
    _inherit = 'sale.rental.report'

    rental_status = fields.Selection([
        ('pickup', "Booked"),
        ('return', "Picked-Up"),
        ('returned', "Returned"),
    ], string="Rental Status", readonly=True)

    def _select(self):
        select_str = super()._select()
        select_str += """,
            CASE
                WHEN sol.qty_delivered < sol.product_uom_qty THEN 'pickup'
                WHEN sol.qty_returned >= sol.qty_delivered THEN 'returned'
                ELSE 'return'
            END as rental_status
        """
        return select_str


    @api.model
    def get_product_chart_data(self, product_id, date_from=None, date_to=None):
        """
        Returns time-series data for line/bar graph visualization
        Data includes: rental trends over time for the selected product
        """
        product = self.env['product.product'].browse(product_id)
        if not product.exists():
            return {
                'line_chart': {
                    'labels': [],
                    'datasets': []
                },
                'pie_chart': {
                    'labels': [],
                    'datasets': [{'data': [], 'backgroundColor': []}]
                }
            }
        
        # Get rental data for this product
        domain = [('product_id', '=', product_id)]
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        
        rental_records = self.search(domain, order='date asc')
        
        # Group data by date for line chart
        date_data = defaultdict(lambda: {
            'quantity': 0.0,
            'revenue': 0.0,
            'qty_delivered': 0.0
        })
        
        # Calculate profit/utilization/status breakdown
        status_data = defaultdict(float)
        profit_data = {
            'total_revenue': 0.0,
            'total_cost': 0.0,
            'total_profit': 0.0
        }
        utilization_data = {
            'rented_days': 0,
            'available_days': 0,
            'utilization_rate': 0.0
        }
        
        for record in rental_records:
            date_str = record.date.strftime('%Y-%m-%d') if record.date else ''
            
            # Time-series data
            date_data[date_str]['quantity'] += record.quantity or 0.0
            date_data[date_str]['revenue'] += record.price or 0.0
            date_data[date_str]['qty_delivered'] += record.qty_delivered or 0.0
            
            # Status breakdown
            status_data[record.state or 'draft'] += record.price or 0.0
            
            # Profit calculation
            profit_data['total_revenue'] += record.price or 0.0
            # Cost calculation (using standard_price if available)
            if record.product_id:
                cost_per_day = record.product_id.standard_price or 0.0
                profit_data['total_cost'] += cost_per_day * (record.quantity or 0.0)
            
            # Utilization
            if record.state in ['sale', 'done']:
                utilization_data['rented_days'] += record.quantity or 0.0
        
        profit_data['total_profit'] = profit_data['total_revenue'] - profit_data['total_cost']
        
        # Prepare line chart data (time-series)
        sorted_dates = sorted(date_data.keys())
        line_chart_data = {
            'labels': sorted_dates,
            'datasets': [
                {
                    'label': 'Quantity',
                    'data': [date_data[d]['quantity'] for d in sorted_dates],
                    'borderColor': '#36A2EB',
                    'backgroundColor': 'rgba(54, 162, 235, 0.1)',
                    'tension': 0.4,
                    'yAxisID': 'y'
                },
                {
                    'label': 'Revenue',
                    'data': [date_data[d]['revenue'] for d in sorted_dates],
                    'borderColor': '#4BC0C0',
                    'backgroundColor': 'rgba(75, 192, 192, 0.1)',
                    'tension': 0.4,
                    'yAxisID': 'y1'
                }
            ]
        }
        
        # Prepare pie chart data for status breakdown
        status_labels = list(status_data.keys())
        status_values = list(status_data.values())
        
        # Color palette for pie chart
        colors = [
            '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', 
            '#9966FF', '#FF9F40', '#FF6384', '#C9CBCF'
        ]
        
        chart_data = {
            'line_chart': line_chart_data,
            'pie_chart': {
                'labels': status_labels,
                'datasets': [{
                    'data': status_values,
                    'backgroundColor': colors[:len(status_labels)]
                }]
            },
            'profit_data': profit_data,
            'utilization_data': utilization_data,
            'product_info': {
                'name': product.name,
                'image_url': '/web/image/product.product/%s/image_128' % product_id if product.image_128 else None
            }
        }
        
        return chart_data


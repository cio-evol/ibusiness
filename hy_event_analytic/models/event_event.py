# -*- coding: utf-8 -*-

from odoo import api, fields, models


class EventEvent(models.Model):
    _inherit = 'event.event'

    event_type = fields.Selection(
        [
            ('donation', 'Donation'),
            ('trip', 'Trip'),
            ('fundraiser', 'Fundraiser'),
        ],
        string='Event Type',
        default='donation',
        required=True,
        help='Type of event: Donation, Trip, or Fundraiser',
        tracking=True,
    )
    allow_donations = fields.Boolean(
        string='Allow Donations',
        default=False,
        help='Enable this to allow donations for this event',
        tracking=True,
    )
    payment_strategy = fields.Selection(
        [
            ('recurring', 'Recurring'),
            ('one_time', 'One Time'),
        ],
        string='Payment Strategy',
        default='one_time',
        help='Payment strategy for donations: Recurring or One Time',
        tracking=True,
    )
    show_ticket_calendar_buttons = fields.Boolean(
        string='Show Ticket & Calendar Buttons',
        default=True,
        help='Show "Download Ticket" and "Add to Calendar" buttons on order confirmation page',
        tracking=True,
    )
    show_seat_count = fields.Boolean(
        string='Show Seat Count',
        default=True,
        help='Show available seat count on event registration page',
        tracking=True,
    )
    show_quantity_selector = fields.Boolean(
        string='Show Quantity Selector',
        default=True,
        help='Show quantity selector (plus/minus buttons) in ticket registration modal',
        tracking=True,
    )

    @api.model
    def _search_get_detail(self, website, order, options):
        """Override to filter events by event_type (donation/trip)"""
        result = super()._search_get_detail(website, order, options)
        
        # Filter by custom event_type if specified in options
        custom_event_type = options.get('custom_event_type')
        if custom_event_type:
            # Add filter to the base_domain list
            result['base_domain'].append([('event_type', '=', custom_event_type)])
            # Also add to no_date_domain and no_country_domain for correct counts
            if 'no_date_domain' in result:
                result['no_date_domain'].append([('event_type', '=', custom_event_type)])
            if 'no_country_domain' in result:
                result['no_country_domain'].append([('event_type', '=', custom_event_type)])
        
        return result


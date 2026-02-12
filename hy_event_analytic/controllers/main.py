# -*- coding: utf-8 -*-

from odoo import http, fields, _
from odoo.http import request
from odoo.fields import Domain
from odoo.addons.website_event.controllers.main import WebsiteEventController


class WebsiteEventTrips(WebsiteEventController):

    def _get_events_search_options(self, slug_tags, **post):
        """Override to add custom_event_type filter"""
        options = super()._get_events_search_options(slug_tags, **post)
        # Add custom event type filter if specified
        if post.get('custom_event_type'):
            options['custom_event_type'] = post['custom_event_type']
        return options

    @http.route(['/trips', '/trips/page/<int:page>'], type='http', auth='public', website=True, sitemap=True)
    def trips(self, page=1, **searches):
        """Show only trip events"""
        searches['custom_event_type'] = 'trip'
        return self.events(page=page, **searches)

    @http.route(['/fundraisers', '/fundraisers/page/<int:page>'], type='http', auth='public', website=True, sitemap=True)
    def fundraisers(self, page=1, **searches):
        """Show only fundraiser events"""
        searches['custom_event_type'] = 'fundraiser'
        return self.events(page=page, **searches)


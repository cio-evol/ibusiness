from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    pdc_blocked = fields.Boolean(
        string='PDC Blocked',
        default=False,
        tracking=True,
        help="When checked, this customer is blocked from creating new PDCs due to returned cheques"
    )
    pdc_block_reason = fields.Text(
        string='PDC Block Reason',
        help="Reason for blocking PDC transactions for this customer"
    )
    pdc_block_date = fields.Date(
        string='PDC Block Date',
        help="Date when customer was blocked from PDC transactions"
    )
    pdc_blocked_by = fields.Many2one(
        'res.users',
        string='PDC Blocked By',
        help="User who blocked this customer for PDC transactions"
    )

    def action_block_pdc(self):
        """Block customer from PDC transactions"""
        self.ensure_one()
        # For now, block immediately with a default reason
        # This can be enhanced with a wizard later if needed
        default_reason = _('Blocked due to returned cheque')
        self.write({
            'pdc_blocked': True,
            'pdc_block_reason': default_reason,
            'pdc_block_date': fields.Date.context_today(self),
            'pdc_blocked_by': self.env.user.id,
        })

        self.message_post(
            body=_('PDC blocked by %s. Reason: %s') % (self.env.user.name, default_reason),
            message_type='notification'
        )

        return True

    def action_unblock_pdc(self):
        """Unblock customer from PDC transactions (requires authorization)"""
        self.ensure_one()

        # Check if user has permission to unblock
        if not self.env.user.has_group('ns_pdc.group_pdc_unblock_manager'):
            raise UserError(_('You do not have permission to unblock PDC for customers. Please contact your administrator.'))

        self.write({
            'pdc_blocked': False,
            'pdc_block_reason': False,
            'pdc_block_date': False,
            'pdc_blocked_by': False,
        })

        self.message_post(
            body=_('PDC unblocked by %s') % self.env.user.name,
            message_type='notification'
        )

    @api.model
    def block_customer_pdc(self, partner_id, reason):
        """Utility method to block customer PDC with reason"""
        partner = self.browse(partner_id)
        partner.write({
            'pdc_blocked': True,
            'pdc_block_reason': reason,
            'pdc_block_date': fields.Date.context_today(self),
            'pdc_blocked_by': self.env.user.id,
        })

        partner.message_post(
            body=_('PDC blocked by %s. Reason: %s') % (self.env.user.name, reason),
            message_type='notification'
        )
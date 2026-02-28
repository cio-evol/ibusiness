# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

"""
Enhanced PDC Payment Wizard with Auto Bill Selection for Vendor Payments

This module has been enhanced to automatically select all unpaid vendor bills
when creating a PDC payment for vendor bills (send_money payment type).
The auto-selection works in the following scenarios:
1. When selecting a vendor bill and creating PDC payment
2. When changing payment type to 'send_money' 
3. When changing partner for 'send_money' payment type
4. When creating PDC payment from vendor bill context
"""


class Attachment(models.Model):
    _inherit = 'ir.attachment'

    pdc_id = fields.Many2one('pdc.wizard')


class PDCWizard(models.Model):
    _name = "pdc.wizard"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = "PDC Wizard"

    # pdc only be allowed to delete in draft state
    def unlink(self):

        for rec in self:
            if rec.state != 'draft':
                raise UserError("You can only delete draft state pdc")

        return super().unlink()

    def action_register_check(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        account_move_model = self.env[active_model].browse(active_id)

        if account_move_model.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError(
                "Only Customer invoice and vendor bills are considered!")

        move_listt = []
        payment_amount = 0.0
        payment_type = ''
        if len(active_ids) > 0:
            account_moves = self.env[active_model].browse(active_ids)
            partners = account_moves.mapped('partner_id')
            if len(set(partners)) != 1:
                raise UserError('Partners must be same')

            states = account_moves.mapped('state')
            if len(set(states)) != 1 or states[0] != 'posted':
                raise UserError(
                    'Only posted invoices/bills are considered for PDC payment!!')

            for account_move in account_moves:
                if account_move.payment_state != 'paid' and account_move.amount_residual != 0.0:
                    payment_amount = payment_amount + account_move.amount_residual
                    move_listt.append(account_move.id)
        if not move_listt:
            raise UserError("Selected invoices/bills are already paid!!")

        if account_moves[0].move_type in ('in_invoice'):
            payment_type = 'send_money'

        if account_moves[0].move_type in ('out_invoice'):
            payment_type = 'receive_money'

        # For vendor bills, auto-select all unpaid bills for the same partner
        if payment_type == 'send_money':
            domain = [('partner_id', '=', account_move_model.partner_id.id), ('payment_state', '!=',
                                                                              'paid'), ('amount_residual', '!=', 0.0), ('state', '=', 'posted'),
                     ('move_type', '=', 'in_invoice')]
            all_unpaid_bills = self.env['account.move'].search(domain)
            if all_unpaid_bills:
                move_listt = all_unpaid_bills.ids
                payment_amount = sum(all_unpaid_bills.mapped('amount_residual'))

        view = self.env.ref("sh_pdc.sh_pdc_wizard_form_wizard", raise_if_not_found=False)
        return {
            "name": "PDC Payment",
            "res_model": "pdc.wizard",
            "view_mode": "form",
            "view_id": view.id if view else False,
            "context": {
                "default_invoice_ids": [(6, 0, move_listt)],
                "default_partner_id": account_move_model.partner_id.id,
                "default_payment_amount": payment_amount,
                "default_payment_type": payment_type,
            },
            "target": "new",
            "type": "ir.actions.act_window",
        }

    def open_attachments(self):
        action = self.env["ir.actions.act_window"]._for_xml_id("base.action_attachment")
        action["domain"] = [("id", "in", self.attachment_ids.ids)]
        return action

    def open_journal_items(self):
        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_account_moves_all")
        lines = self.env["account.move.line"].search([("pdc_id", "=", self.id)])
        action["domain"] = [("id", "in", lines.ids)] if lines else [("id", "=", False)]
        return action

    def open_journal_entry(self):
        action = self.env["ir.actions.act_window"]._for_xml_id("sh_pdc.sh_pdc_action_move_journal_line")
        moves = self.env["account.move"].search([("pdc_id", "=", self.id)])
        action["domain"] = [("id", "in", moves.ids)]
        return action

    @api.model
    def default_get(self, fields):
        rec = super().default_get(fields)
        active_ids = self._context.get('active_ids')
        active_model = self._context.get('active_model')

        # Check for selected invoices ids
        if not active_ids or active_model != 'account.move':
            return rec
        invoices = self.env['account.move'].browse(active_ids)
        if invoices and len(invoices) == 1:
            invoice = invoices[0]
            if invoice.move_type in ('out_invoice', 'out_refund'):
                rec.update({'payment_type': 'receive_money'})
            elif invoice.move_type in ('in_invoice', 'in_refund'):
                rec.update({'payment_type': 'send_money'})

            rec.update({'partner_id': invoice.partner_id.id,
                        'payment_amount': invoice.amount_residual,
                        'invoice_id': invoice.id,
                        'due_date': invoice.invoice_date_due,
                        'memo': invoice.name})
            
            # Auto-select all unpaid bills for vendor payments
            if invoice.move_type in ('in_invoice', 'in_refund'):
                domain = [('partner_id', '=', invoice.partner_id.id), ('payment_state', '!=',
                                                                        'paid'), ('amount_residual', '!=', 0.0), ('state', '=', 'posted'),
                         ('move_type', '=', 'in_invoice')]
                moves = self.env['account.move'].search(domain)
                if moves:
                    rec.update({'invoice_ids': [(6, 0, moves.ids)]})

        return rec

    name = fields.Char("Name", default='New', readonly=True, tracking=True)
    # check_amount_in_words = fields.Char(string="Amount in Words",compute='_compute_check_amount_in_words')
    payment_type = fields.Selection([('receive_money', 'Receive Money'), (
        'send_money', 'Send Money')], string="Payment Type", default='receive_money', tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string="Partner", tracking=True)
    payment_amount = fields.Monetary("Payment Amount", tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string="Currency", default=lambda self: self.env.company.currency_id, tracking=True)
    reference = fields.Char("Cheque Reference", tracking=True)
    journal_id = fields.Many2one('account.journal', string="Payment Journal", domain=[
                                 ('type', '=', 'bank')], required=False, tracking=True)
    cheque_status = fields.Selection([('draft', 'Draft'), ('deposit', 'Deposit'), (
        'paid', 'Paid')], string="Cheque Status", default='draft', tracking=True)
    payment_date = fields.Date(
        "Payment Date", default=fields.Date.today(), required=True, tracking=True)
    due_date = fields.Date("Due Date", required=True, tracking=True)
    memo = fields.Char("Memo", tracking=True)
    agent = fields.Char("Agent", tracking=True)
    bank_id = fields.Many2one('res.bank', string="Bank", tracking=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', 'pdc_attachment_rel', string='Cheque Image')
    company_id = fields.Many2one(
        'res.company', string='company', default=lambda self: self.env.company, tracking=True)
    invoice_id = fields.Many2one(
        'account.move', string="Invoice/Bill", tracking=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("registered", "Registered"),
        ("deposited", "Deposited"),
        ("returned", "Returned"),
        ("bounced", "Bounced"),
        ("done", "Done"),
        ("cancel", "Cancelled"),
    ], string="State", default="draft", tracking=True)

    # state = fields.Selection([('draft', 'Draft'), ('registered', 'Registered'), ('returned', 'Returned'),
    #                           ('deposited', 'Deposited'), ('bounced', 'Bounced'), ('done', 'Done'), ('cancel', 'Cancelled')], string="State", default='draft', tracking=True)

    deposited_debit = fields.Many2one('account.move.line')
    deposited_credit = fields.Many2one('account.move.line')

    invoice_ids = fields.Many2many('account.move')
    account_move_ids = fields.Many2many(
        'account.move', compute="compute_account_moves",)
    done_date = fields.Date(string="Done Date", readonly=True, tracking=True)

    @api.depends('payment_type', 'partner_id')
    def compute_account_moves(self):

        self.account_move_ids = False
        domain = [('partner_id', '=', self.partner_id.id), ('payment_state', '!=',
                                                            'paid'), ('amount_residual', '!=', 0.0), ('state', '=', 'posted')]

        if self.payment_type == 'receive_money':
            domain.extend([('move_type', '=', 'out_invoice')])

        else:
            domain.extend([('move_type', '=', 'in_invoice')])

        moves = self.env['account.move'].search(domain)
        self.account_move_ids = moves.ids

    @api.onchange('partner_id')
    def _onchange_partner(self):
        # Auto-select bills for vendor payments (send_money) regardless of company setting
        if self.payment_type == 'send_money' or self.env.company.auto_fill_open_invoice:
            domain = [('partner_id', '=', self.partner_id.id), ('payment_state', '!=',
                                                                'paid'), ('amount_residual', '!=', 0.0), ('state', '=', 'posted')]

            if self.payment_type == 'receive_money':
                domain.extend([('move_type', '=', 'out_invoice')])
            else:
                domain.extend([('move_type', '=', 'in_invoice')])

            moves = self.env['account.move'].search(domain)
            self.invoice_ids = [(6, 0, moves.ids)]

    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        """Auto-select bills when payment type is send_money (vendor bills)"""
        if self.payment_type == 'send_money' and self.partner_id:
            domain = [('partner_id', '=', self.partner_id.id), ('payment_state', '!=',
                                                                'paid'), ('amount_residual', '!=', 0.0), ('state', '=', 'posted'),
                     ('move_type', '=', 'in_invoice')]
            moves = self.env['account.move'].search(domain)
            self.invoice_ids = [(6, 0, moves.ids)]

    # Register pdc payment
    def button_register(self):
        listt = []
        if self:

            if self.invoice_id:
                listt.append(self.invoice_id.id)
            if self.invoice_ids:
                listt.extend(self.invoice_ids.ids)

            self.write({
                'invoice_ids': [(6, 0, list(set(listt)))]
            })

            if self.cheque_status == 'draft':
                self.write({'state': 'draft'})

            if self.cheque_status == 'deposit':
                self.action_register()
                self.action_deposited()
                self.write({'state': 'deposited'})

            if self.cheque_status == 'paid':
                self.action_register()
                self.action_deposited()
                self.action_done()
                self.write({'state': 'done'})

    def action_register(self):
        self.check_payment_amount()

        if self.invoice_ids:
            list_amount_residuals = self.invoice_ids.mapped('amount_residual')
            amount = (self.currency_id.round(sum(list_amount_residuals))
                      if self.currency_id else round(sum(list_amount_residuals), 2))

            # if self.payment_amount > amount and amount != 0:
            #     raise UserError(
            #         "Payment amount is greater than total invoice/bill amount!!!")

        # Create simple journal entry for cheque in hand
        # Create a journal entry: debit cheque_in_hand (asset), credit receivable (customer)
        if self.payment_type == 'receive_money' and self.env.company.cheque_in_hand:
            # Get the default account for the cheque in hand journal
            cheque_in_hand_account = self.env.company.cheque_in_hand.default_account_id
            if not cheque_in_hand_account:
                raise UserError("Please configure default account for Cheque In-Hand journal!")
            
            move_vals = {
                'date': fields.Date.today(),
                'journal_id': self.env.company.cheque_in_hand.id,
                'partner_id': self.partner_id.id,
                'ref': f"PDC - {self.memo or 'Cheque'}",
                'move_type': 'entry',
                'pdc_id': self.id,
                'line_ids': [
                    (0, 0, {
                        'account_id': cheque_in_hand_account.id,
                        'debit': self.payment_amount,
                        'credit': 0.0,
                        'partner_id': self.partner_id.id,
                        'pdc_id': self.id
                    }),
                    (0, 0, {
                        'account_id': self.partner_id.property_account_receivable_id.id,
                        'credit': self.payment_amount,
                        'debit': 0.0,
                        'partner_id': self.partner_id.id,
                        'pdc_id': self.id
                    }),
                ]
            }
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            
            # Reconcile with specific invoices to reduce amount_residual
            if self.invoice_ids:
                receivable_lines = move.line_ids.filtered(lambda l: l.account_id == self.partner_id.property_account_receivable_id)
                for invoice in self.invoice_ids:
                    if invoice.amount_residual > 0:
                        invoice_lines = invoice.line_ids.filtered(lambda l: l.account_id == self.partner_id.property_account_receivable_id and not l.reconciled)
                        if receivable_lines and invoice_lines:
                            (receivable_lines | invoice_lines).reconcile()
            
            self.write({'state': 'registered'})

    def check_payment_amount(self):
        if self.payment_amount <= 0.0:
            raise UserError("Amount must be greater than zero!")


    def check_pdc_account(self):
        if self.payment_type == 'receive_money':
            if not self.env.company.pdc_customer:
                raise UserError(
                    "Please Set PDC payment account for Customer !")
            else:
                return self.env.company.pdc_customer.id

        else:
            if not self.env.company.pdc_vendor:
                raise UserError(
                    "Please Set PDC payment account for Supplier !")
            else:
                return self.env.company.pdc_vendor.id

    def get_partner_account(self):
        if self.payment_type == 'receive_money':
            return self.partner_id.property_account_receivable_id.id
        else:
            return self.partner_id.property_account_payable_id.id

    def action_returned(self):
        """Open PDC return wizard"""
        return {
            'name': 'PDC Return',
            'type': 'ir.actions.act_window',
            'res_model': 'pdc.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_pdc_id': self.id}
        }

    def get_credit_move_line(self, account):
        return {
            'pdc_id': self.id,
            #             'partner_id': self.partner_id.id,
            'account_id': account,
            'credit': self.payment_amount,
            'ref': self.memo,
            'date': fields.Date.today(),
            'date_maturity': self.due_date,
        }

    def get_debit_move_line(self, account):
        return {
            'pdc_id': self.id,
            #             'partner_id': self.partner_id.id,
            'account_id': account,
            'debit': self.payment_amount,
            'ref': self.memo,
            'date': fields.Date.today(),
            'date_maturity': self.due_date,
        }

    def get_move_vals(self, debit_line, credit_line):
        return {
            'pdc_id': self.id,
            'date': fields.Date.today(),
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.id,
            'ref': self.memo,
            'move_type': 'entry',
            'line_ids': [(0, 0, debit_line),
                         (0, 0, credit_line)]
        }

    def action_deposited(self):
        move = self.env['account.move']

        self.check_payment_amount()  # amount must be positive
        pdc_account = self.check_pdc_account()

        # Create Journal Item - Move from Cheque In-Hand to Payment Journal (Bank)
        if self.payment_type == 'receive_money' and self.env.company.cheque_in_hand:
            # For customer: Move from Cheque In-Hand to Payment Journal (Bank Account)
            cheque_in_hand_account = self.env.company.cheque_in_hand.default_account_id
            if not cheque_in_hand_account:
                raise UserError("Please configure default account for Cheque In-Hand journal!")
            
            # Get the bank account from the payment journal
            if not self.journal_id:
                raise UserError("Please select a Payment Journal for deposit!")
            
            # Use inbound payment method line for debit (money coming into bank)
            inbound_accounts = self.journal_id._get_journal_inbound_outstanding_payment_accounts()
            if not inbound_accounts:
                raise UserError("Please configure inbound payment method line for Payment Journal!")
            inbound_account = inbound_accounts[0].id
            
            # Use outbound payment method line for credit (money going out of temporary account)
            outbound_accounts = self.journal_id._get_journal_outbound_outstanding_payment_accounts()
            if not outbound_accounts:
                raise UserError("Please configure outbound payment method line for Payment Journal!")
            outbound_account = outbound_accounts[0].id
            
            # Debit: Inbound account (money coming into bank)
            # Credit: Outbound account (money going out of temporary account)
            move_line_vals_debit = self.get_debit_move_line(inbound_account)
            # move_line_vals_credit = self.get_credit_move_line(outbound_account)
            move_line_vals_credit = self.get_credit_move_line(cheque_in_hand_account.id)
        else:
            # For vendor: Use original logic
            partner_account = self.get_partner_account()
            move_line_vals_debit = self.get_debit_move_line(partner_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        # Update state to deposited
        self.write({'state': 'deposited'})

        # Always create and post journal entry when depositing, regardless of invoice status
        if not self.journal_id.id:
            raise UserError(_("Please Set Payment Journal"))
        move_id = move.create(move_vals)
        move_id.action_post()

        self.write({'deposited_debit': move_id.line_ids.filtered(lambda x: x.debit > 0),
                    'deposited_credit': move_id.line_ids.filtered(lambda x: x.credit > 0)})


    def action_done(self):
        move = self.env['account.move']

        self.check_payment_amount()  # amount must be positive
        pdc_account = self.check_pdc_account()
        bank_account = False
        if self.payment_type == 'receive_money':
            bank_account = self.journal_id._get_journal_inbound_outstanding_payment_accounts()
        else:
            bank_account = self.journal_id._get_journal_outbound_outstanding_payment_accounts()
        bank_account = bank_account[0].id if bank_account else False

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(bank_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(bank_account)

        if self.memo:
            move_line_vals_debit.update(
                {'name': 'PDC Payment :'+self.memo, 'partner_id': self.partner_id.id})
            move_line_vals_credit.update(
                {'name': 'PDC Payment :'+self.memo, 'partner_id': self.partner_id.id})
        else:
            move_line_vals_debit.update(
                {'name': 'PDC Payment', 'partner_id': self.partner_id.id})
            move_line_vals_credit.update(
                {'name': 'PDC Payment', 'partner_id': self.partner_id.id})

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        # invoice = self.env['account.move'].sudo().search([('name','=',self.memo)])
        # if invoice:
        total_amount_residuals = sum(
            self.invoice_ids.mapped('amount_residual'))
        if self.invoice_ids and total_amount_residuals != 0:
            move_id = move.create(move_vals)
            move_id.action_post()

            payment_amount = self.payment_amount
            for invoice in self.invoice_ids:

                if self.payment_type == 'receive_money':
                    # reconcilation Entry for Invoice
                    debit_move_id = self.env['account.move.line'].sudo().search([('move_id', '=', invoice.id),
                                                                                 ('debit', '>', 0.0)], limit=1)

                    credit_move_id = self.env['account.move.line'].sudo().search([('move_id', '=', move_id.id),
                                                                                  ('credit', '>', 0.0)], limit=1)

                    if debit_move_id and credit_move_id and payment_amount > 0:
                        # self.env['account.full.reconcile'].sudo().create({
                        # })
                        if payment_amount > invoice.amount_residual:
                            amount = invoice.amount_residual

                        else:
                            amount = payment_amount

                        payment_amount -= invoice.amount_residual
                        self.env['account.partial.reconcile'].sudo().create({'debit_move_id': debit_move_id.id,
                                                                                                      'credit_move_id': credit_move_id.id,
                                                                                                      'amount': amount,
                                                                                                      'debit_amount_currency': amount,
                                                                                                      'credit_amount_currency': 0
                                                                                                      })

                        partial_reconcile_id_2 = self.env['account.partial.reconcile'].sudo().create({'debit_move_id': self.deposited_debit.id,
                                                                                                      'credit_move_id': self.deposited_credit.id,
                                                                                                      'amount': amount,
                                                                                                      'debit_amount_currency': amount,
                                                                                                      'credit_amount_currency': 0
                                                                                                      })

                        if invoice.amount_residual == 0:
                            involved_lines = []

                            debit_invoice_line_id = self.env['account.move.line'].search(
                                [('move_id', '=', invoice.id), ('debit', '>', 0)], limit=1)
                            partial_reconcile_ids = self.env['account.partial.reconcile'].sudo().search(
                                [('debit_move_id', '=', debit_invoice_line_id.id)])

                            for partial_reconcile_id in partial_reconcile_ids:
                                involved_lines.append(
                                    partial_reconcile_id.credit_move_id.id)
                                involved_lines.append(
                                    partial_reconcile_id.debit_move_id.id)
                            self.env['account.full.reconcile'].create({
                                'partial_reconcile_ids': [(6, 0, partial_reconcile_ids.ids)],
                                'reconciled_line_ids': [(6, 0, involved_lines)],
                            })

                        involved_lines = [
                            self.deposited_debit.id, self.deposited_credit.id]

                        self.env['account.full.reconcile'].create({
                            'partial_reconcile_ids': [(6, 0, [partial_reconcile_id_2.id])],
                            'reconciled_line_ids': [(6, 0, involved_lines)],
                        })

                else:
                    # reconcilation Entry for Invoice
                    credit_move_id = self.env['account.move.line'].sudo().search([('move_id', '=', invoice.id),
                                                                                  ('credit', '>', 0.0)], limit=1)

                    debit_move_id = self.env['account.move.line'].sudo().search([('move_id', '=', move_id.id),
                                                                                 ('debit', '>', 0.0)], limit=1)

                    if debit_move_id and credit_move_id and payment_amount > 0:
                        if payment_amount > invoice.amount_residual:
                            amount = invoice.amount_residual

                        else:
                            amount = payment_amount

                        payment_amount -= invoice.amount_residual

                        self.env['account.partial.reconcile'].sudo().create({'debit_move_id': debit_move_id.id,
                                                                                                      'credit_move_id': credit_move_id.id,
                                                                                                      'amount': amount,
                                                                                                      'credit_amount_currency': amount,
                                                                                                      'debit_amount_currency': 0
                                                                                                      })
                        partial_reconcile_id_2 = self.env['account.partial.reconcile'].sudo().create({'debit_move_id': self.deposited_debit.id,
                                                                                                      'credit_move_id': self.deposited_credit.id,
                                                                                                      'amount': amount,
                                                                                                      'debit_amount_currency': amount,
                                                                                                      'credit_amount_currency': 0
                                                                                                      })

                        if invoice.amount_residual == 0:
                            involved_lines = []

                            credit_invoice_line_id = self.env['account.move.line'].search(
                                [('move_id', '=', invoice.id), ('credit', '>', 0)], limit=1)
                            partial_reconcile_ids = self.env['account.partial.reconcile'].sudo().search(
                                [('credit_move_id', '=', credit_invoice_line_id.id)])

                            for partial_reconcile_id in partial_reconcile_ids:
                                involved_lines.append(
                                    partial_reconcile_id.credit_move_id.id)
                                involved_lines.append(
                                    partial_reconcile_id.debit_move_id.id)
                            self.env['account.full.reconcile'].create({
                                'partial_reconcile_ids': [(6, 0, partial_reconcile_ids.ids)],
                                'reconciled_line_ids': [(6, 0, involved_lines)],
                            })

                        involved_lines = [
                            self.deposited_debit.id, self.deposited_credit.id]

                        self.env['account.full.reconcile'].create({
                            'partial_reconcile_ids': [(6, 0, [partial_reconcile_id_2.id])],
                            'reconciled_line_ids': [(6, 0, involved_lines)],
                        })

        else:
            bank_account = self.journal_id._get_journal_inbound_outstanding_payment_accounts()
            bank_account = bank_account[0].id if bank_account else False

            partner_account = self.get_partner_account()

            debit_move_line = {
                'pdc_id': self.id,
                'partner_id': self.partner_id.id,
                'account_id': bank_account if self.payment_type == 'receive_money' else partner_account,
                'debit': self.payment_amount,
                'ref': self.memo,
                'date': self.due_date,
                'date_maturity': self.due_date,
            }

            credit_move_line = {
                'pdc_id': self.id,
                'partner_id': self.partner_id.id,
                'account_id': partner_account if self.payment_type == 'receive_money' else bank_account,
                'credit': self.payment_amount,
                'ref': self.memo,
                'date': self.due_date,
                'date_maturity': self.due_date,
            }

            move_vals = {
                'pdc_id': self.id,
                'date': self.due_date,
                'journal_id': self.journal_id.id,
                'ref': self.memo,
                'line_ids': [(0, 0, debit_move_line),
                             (0, 0, credit_move_line)]
            }

            move = self.env['account.move'].create(move_vals)
            move.action_post()

        self.write({
            'state': 'done',
            'done_date': date.today(),
        })

    # form view cancel button
    def action_cancel(self):
        self.action_delete_related_moves()
        if self.company_id.pdc_operation_type == 'cancel':
            self.write({'state': 'cancel'})

        elif self.company_id.pdc_operation_type == 'cancel_draft':
            self.write({'state': 'draft'})

        elif self.company_id.pdc_operation_type == 'cancel_delete':
            self.write({'state': 'draft'})
            self.unlink()
            return {'type': 'ir.actions.act_window_close'}

    # multi action methods
    def action_pdc_cancel(self):
        self.action_delete_related_moves()
        self.write({'state': 'cancel'})

    def action_pdc_cancel_draft(self):
        self.action_delete_related_moves()
        self.write({'state': 'draft'})

    def action_pdc_cancel_delete(self):
        self.action_delete_related_moves()
        self.write({'state': 'draft'})
        self.unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                if vals.get("payment_type") == "receive_money":
                    vals["name"] = self.env["ir.sequence"].next_by_code("pdc.payment.customer") or "New"
                elif vals.get("payment_type") == "send_money":
                    vals["name"] = self.env["ir.sequence"].next_by_code("pdc.payment.vendor") or "New"
        res = super().create(vals_list)
        for rec in res:
            if rec.attachment_ids:
                rec.attachment_ids.write({"res_id": rec.id, "res_model": "pdc.wizard"})
        return res

    # ==============================
    #    CRON SCHEDULER CUSTOMER
    # ==============================
    @api.model
    def notify_customer_due_date(self):
        emails = []
        if self.env.company.is_cust_due_notify:
            notify_day_1 = self.env.company.notify_on_1
            notify_day_2 = self.env.company.notify_on_2
            notify_day_3 = self.env.company.notify_on_3
            notify_day_4 = self.env.company.notify_on_4
            notify_day_5 = self.env.company.notify_on_5
            notify_date_1 = False
            notify_date_2 = False
            notify_date_3 = False
            notify_date_4 = False
            notify_date_5 = False
            if notify_day_1:
                notify_date_1 = fields.Date.today() + timedelta(days=int(notify_day_1) * -1)
            if notify_day_2:
                notify_date_2 = fields.Date.today() + timedelta(days=int(notify_day_2) * -1)
            if notify_day_3:
                notify_date_3 = fields.Date.today() + timedelta(days=int(notify_day_3) * -1)
            if notify_day_4:
                notify_date_4 = fields.Date.today() + timedelta(days=int(notify_day_4) * -1)
            if notify_day_5:
                notify_date_5 = fields.Date.today() + timedelta(days=int(notify_day_5) * -1)

            records = self.search([('payment_type', '=', 'receive_money')])
            for user in self.env.company.sh_user_ids:
                if user.partner_id and user.partner_id.email:
                    emails.append(user.partner_id.email)
            email_values = {
                'email_to': ','.join(emails),
            }
            view = self.env.ref(
                "sh_pdc.sh_pdc_payment_form_view",
                raise_if_not_found=False,
            ).sudo()
            view_id = view.id if view else 0
            for record in records:
                if (record.due_date == notify_date_1
                    or record.due_date == notify_date_2
                    or record.due_date == notify_date_3
                    or record.due_date == notify_date_4
                        or record.due_date == notify_date_5):

                    if self.env.company.is_notify_to_customer:
                        # template_download_id = record.env['ir.model.data'].get_object(
                        #     'sh_pdc', 'sh_pdc_company_to_customer_notification_1'
                        #     )
                        template_download_id = self.env.ref(
                            'sh_pdc.sh_pdc_company_to_customer_notification_1')
                        _ = record.env['mail.template'].browse(
                            template_download_id.id
                        ).send_mail(record.id, email_layout_xmlid='mail.mail_notification_light', force_send=True)
                    if self.env.company.is_notify_to_user and self.env.company.sh_user_ids:
                        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
                        url = f"{base_url}/web#id={record.id}&model=pdc.wizard&view_type=form&view_id={view_id}"
                        ctx = {"customer_url": url}
                        template = self.env.ref(
                            "sh_pdc.sh_pdc_company_to_int_user_notification_1",
                            raise_if_not_found=False,
                        )
                        if template:
                            template.sudo().with_context(ctx).send_mail(
                                record.id,
                                email_values=email_values,
                                email_layout_xmlid="mail.mail_notification_light",
                                force_send=True,
                            )

    # ==============================
    #    CRON SCHEDULER VENDOR
    # ==============================


    # Multi Action Starts for change the state of PDC check

    def action_set_draft(self):
        self.action_delete_related_moves()
        self.sudo().write({
            'state': 'draft',
        })

    def action_delete_related_moves(self):
        for model in self:
            move_ids = self.env["account.move"].search([("pdc_id", "=", model.id)])
            for move in move_ids:
                try:
                    if move.state == "posted":
                        move.button_draft()
                    move.unlink()
                except Exception:
                    pass
            model.sudo().write({"done_date": False})

    def action_state_register(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'draft':
                    for active_model in active_models:
                        active_model.action_register()
                else:
                    raise UserError(
                        "Only Draft state PDC check can switch to Register state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_return(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'registered':
                    for active_model in active_models:
                        active_model.action_returned()
                else:
                    raise UserError(
                        "Only Register state PDC check can switch to return state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_deposit(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] in ['registered', 'returned', 'bounced']:
                    for active_model in active_models:
                        active_model.action_deposited()
                else:
                    raise UserError(
                        "Only Register,Return and Bounce state PDC check can switch to Deposit state!!")
            else:
                raise UserError(
                    "States must be same!!")


    def action_state_done(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'deposited':
                    for active_model in active_models:
                        active_model.action_done()
                else:
                    raise UserError(
                        "Only Deposit state PDC check can switch to Done state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_cancel(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] in ['registered', 'returned', 'bounced']:
                    for active_model in active_models:
                        active_model.action_cancel()
                else:
                    raise UserError(
                        "Only Register,Return and Bounce state PDC check can switch to Cancel state!!")
            else:
                raise UserError(
                    "States must be same!!")

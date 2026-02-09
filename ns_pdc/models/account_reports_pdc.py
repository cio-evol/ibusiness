import re
from odoo import models, api


class AgedReceivableCustomHandler(models.AbstractModel):
    _inherit = 'account.aged.receivable.report.handler'

    def _custom_line_postprocessor(self, report, options, lines):
        """
        Add Total PDC Amount per line (invoice/move/partner) to the report lines.
        """
        lines = super()._custom_line_postprocessor(report, options, lines)

        PDC = self.env['account.pdc']

        for line in lines:
            total_pdc = 0.0
            move_id = None
            partner_id = None

            if line.get("id"):
                match_move = re.search(r'~account\.move~(\d+)', line['id'])
                if match_move:
                    move_id = int(match_move.group(1))

                match_mline = re.search(r'~account\.move\.line~(\d+)', line['id'])
                if match_mline:
                    line_id = int(match_mline.group(1))
                    mline = self.env['account.move.line'].browse(line_id)
                    if mline.exists():
                        move_id = mline.move_id.id

                match_partner = re.search(r'~res\.partner~(\d+)', line['id'])
                if match_partner:
                    partner_id = int(match_partner.group(1))

            pdcs = self.env['account.pdc'].browse()
            if move_id:
                if 'invoice_id' in PDC._fields:
                    pdcs = PDC.search([('invoice_id', '=', move_id)])
                elif 'move_id' in PDC._fields:
                    pdcs = PDC.search([('move_id', '=', move_id)])
            elif partner_id:
                if 'partner_id' in PDC._fields:
                    pdcs = PDC.search([('partner_id', '=', partner_id)])

            total_pdc = sum(pdc.amount for pdc in pdcs) if pdcs else 0.0

            total_pdc_str = f"{total_pdc:,.2f}" if total_pdc else ""

            if 'columns' not in line:
                line['columns'] = []

            # Check if column exists
            for column in line['columns']:
                if column.get('expression_label') == 'total_pdc_amount':
                    column['name'] = total_pdc_str
                    column['figure_type'] = 'monetary'
                    column['currency_id'] = self.env.company.currency_id.id
                    column['style'] = 'text-align:right; font-color:red; font-weight:bold;'

        return lines


class AgepayableCustomHandler(models.AbstractModel):
    _inherit = 'account.aged.payable.report.handler'

    def _custom_line_postprocessor(self, report, options, lines):
        lines = super()._custom_line_postprocessor(report, options, lines)

        PDC = self.env['account.pdc']

        for line in lines:
            total_pdc = 0.0
            move_id = None
            partner_id = None

            # 🔹 Extract ids
            if line.get("id"):
                match_move = re.search(r'~account\.move~(\d+)', line['id'])
                if match_move:
                    move_id = int(match_move.group(1))

                match_mline = re.search(r'~account\.move\.line~(\d+)', line['id'])
                if match_mline:
                    mline = self.env['account.move.line'].browse(int(match_mline.group(1)))
                    if mline.exists():
                        move_id = mline.move_id.id

                match_partner = re.search(r'~res\.partner~(\d+)', line['id'])
                if match_partner:
                    partner_id = int(match_partner.group(1))


            if move_id:
                move = self.env['account.move'].browse(move_id)
                if move.exists() and move.move_type in ['in_invoice', 'in_refund']:
                    if 'invoice_id' in PDC._fields:
                        pdcs = PDC.search([('invoice_id', '=', move_id)])
                    elif 'move_id' in PDC._fields:
                        pdcs = PDC.search([('move_id', '=', move_id)])
                    else:
                        pdcs = self.env['account.pdc']
                    total_pdc = sum(pdc.amount for pdc in pdcs)


            elif partner_id:
                partner = self.env['res.partner'].browse(partner_id)
                if partner.exists():
                    domain = [('partner_id', '=', partner_id)]
                    # Only link to bills
                    if 'invoice_id' in PDC._fields:
                        domain.append(('invoice_id.move_type', 'in', ['in_invoice', 'in_refund']))
                    elif 'move_id' in PDC._fields:
                        domain.append(('move_id.move_type', 'in', ['in_invoice', 'in_refund']))
                    pdcs = PDC.search(domain)
                    total_pdc = sum(pdc.amount for pdc in pdcs)


            total_pdc_str = f"{total_pdc:,.2f}" if total_pdc else ""


            if 'columns' not in line:
                line['columns'] = []

            for column in line['columns']:
                if column.get('expression_label') == 'total_pdc_amount':
                    column['name'] = total_pdc_str
                    column['figure_type'] = 'monetary'
                    column['currency_id'] = self.env.company.currency_id.id
                    column['style'] = 'text-align:right; color:red; font-weight:bold;'

        return lines




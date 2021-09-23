import base64
from io import BytesIO
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.tools.translate import _
import xlrd
import logging
_logger = logging.getLogger(__name__)


class WizImport(models.TransientModel):
    _name = 'wiz.import'
    _description = 'Import'

    data_sheet = fields.Binary('Import File')
    import_table = fields.Selection([('sia_level1', 'Level 1'), ('sia_level2', 'Level 2'), ('sia_level3', 'Level 3')], string='Import Table', required=True)

    @api.multi
    def upload_level1_data(self):
        file_name = self.data_sheet
        if not file_name:
            raise UserError(_('Please Choose The File!'))
        val = base64.decodestring(file_name)
        fp = BytesIO()
        fp.write(val)
        wb = xlrd.open_workbook(file_contents=fp.getvalue())
        wb.sheet_names()
        sheet_name = wb.sheet_names()
        sh = wb.sheet_by_index(0)
        sh = wb.sheet_by_name(sheet_name[0])
        n_rows = sh.nrows
        for row in range(1, n_rows):
            if sh.row_values(row) and sh.row_values(row)[0]:
                name = str(sh.row_values(row)[0])
                desc = str(sh.row_values(row)[1])
                area_type = str(sh.row_values(row)[2])
                level1_id = self.env['subject.industrial.area.level1'].search([('name', '=', name),('area_type', '=', area_type)], limit=1)
                if not level1_id:
                    self._cr.execute('INSERT INTO subject_industrial_area_level1(name,description,area_type) values (%s,%s,%s) RETURNING id',
                                 (name, desc, area_type))

        return True

    @api.multi
    def upload_level2_data(self):
        file_name = self.data_sheet
        if not file_name:
            raise UserError(_('Please Choose The File!'))
        val = base64.decodestring(file_name)
        fp = BytesIO()
        fp.write(val)
        wb = xlrd.open_workbook(file_contents=fp.getvalue())
        wb.sheet_names()
        sheet_name = wb.sheet_names()
        sh = wb.sheet_by_index(0)
        sh = wb.sheet_by_name(sheet_name[0])
        n_rows = sh.nrows
        for row in range(1, n_rows):
            if sh.row_values(row) and sh.row_values(row)[0]:
                subject_area_parent = str(sh.row_values(row)[0])
                name = str(sh.row_values(row)[1])
                desc = str(sh.row_values(row)[2])
                area_type = str(sh.row_values(row)[3])
                sa1_id = self.env['subject.industrial.area.level1'].search([('name', '=', subject_area_parent),('area_type', '=', area_type)], limit=1)
                sa2_level_id = self.env['subject.industrial.area.level2'].search([('level1_id', '=', sa1_id.id),('area_type', '=', area_type)], limit=1)
                sa2_line_id = self.env['subject.industrial.area.level2.line'].search([('level2_id', '=', sa2_level_id.id),('name', '=', name)],limit=1)
                if not sa1_id:
                    # If not record match in SA level1 then create here.
                    self._cr.execute('INSERT INTO subject_industrial_area_level1(name,description,area_type) values (%s,%s,%s) RETURNING id',
                                 (subject_area_parent, desc, area_type))
                    sa1_id = self._cr.fetchone()[0]
                    # Record Inserted into SA level2
                    self._cr.execute('INSERT INTO subject_industrial_area_level2(level1_id,area_type) values (%s,%s) RETURNING id', (sa1_id,area_type))
                    query1 = self._cr.fetchone()[0]
                    # Record Inserted into SA level2 line.
                    if not sa2_line_id:
                        self._cr.execute('INSERT INTO subject_industrial_area_level2_line(level2_id,name,'
                                         'description) values (%s,%s,%s) RETURNING id', (query1, name, desc))
                # If not match record into SA level2 then create here
                elif not sa2_level_id:
                    self._cr.execute('INSERT INTO subject_industrial_area_level2(level1_id,area_type) '
                                     'values (%s,%s) RETURNING id', (sa1_id.id, area_type))
                    query2 = self._cr.fetchone()[0]
                    self._cr.execute('INSERT INTO subject_industrial_area_level2_line(level2_id,name,'
                                     'description) values (%s,%s,%s) RETURNING id', (query2, name, desc))
                # Record inserted into SA2 level line
                elif sa2_level_id:
                    if not sa2_line_id:
                        self._cr.execute('INSERT INTO subject_industrial_area_level2_line(level2_id,name,'
                                         'description) values (%s,%s,%s) RETURNING id', (sa2_level_id.id, name, desc))

        return True

    @api.multi
    def upload_level3_data(self):
        file_name = self.data_sheet
        if not file_name:
            raise UserError(_('Please Choose The File!'))
        val = base64.decodestring(file_name)
        fp = BytesIO()
        fp.write(val)
        wb = xlrd.open_workbook(file_contents=fp.getvalue())
        wb.sheet_names()
        sheet_name = wb.sheet_names()
        sh = wb.sheet_by_index(0)
        sh = wb.sheet_by_name(sheet_name[0])
        n_rows = sh.nrows
        try:
            for row in range(1, n_rows):
                if sh.row_values(row) and sh.row_values(row)[0]:
                    level1 = str(sh.row_values(row)[0])
                    level2 = str(sh.row_values(row)[1])
                    level3 = str(sh.row_values(row)[2])
                    desc   = str(sh.row_values(row)[3])
                    area_type = str(sh.row_values(row)[4])
                    sa1_level_id = self.env['subject.industrial.area.level1'].search([('name', '=', level1),('area_type', '=', area_type)], limit=1)
                    sa2_level_id = self.env['subject.industrial.area.level2'].search([('level1_id', '=', sa1_level_id.id), ('area_type', '=', area_type)], limit=1)
                    sa2_level_line_id = self.env['subject.industrial.area.level2.line'].search([('name', '=', level2),('level2_id.level1_id.name','=ilike', level1)], limit=1)
                    sa3_level_id = self.env['subject.industrial.area.level3'].search([('parent_level2_line_id', '=', sa2_level_line_id.id)], limit=1)
                    sa3_level_line_id = self.env['subject.industrial.area.level3.line'].search([('level3_id', '=', sa3_level_id.id), ('name', '=', level3)], limit=1)

                    flag = False
                    sa1_id = sa1_level_id.id
                    if not sa1_level_id:
                        # If not record match in SA level1 then create here.
                        self._cr.execute(
                            'INSERT INTO subject_industrial_area_level1(name,description,area_type) values (%s,%s,%s) RETURNING id',
                            (level1, desc, area_type))
                        sa1_id = self._cr.fetchone()[0]
                        # Record Inserted into SA level2
                        self._cr.execute(
                            'INSERT INTO subject_industrial_area_level2(level1_id,area_type) values (%s,%s) RETURNING id',
                            (sa1_id, area_type))
                        query1 = self._cr.fetchone()[0]
                        # Record Inserted into SA level2 line.
                        if not sa2_level_line_id:
                            self._cr.execute('INSERT INTO subject_industrial_area_level2_line(level2_id,name,'
                                             'description) values (%s,%s,%s) RETURNING id', (query1, level2, desc))
                        sa2_line_id = self._cr.fetchone()[0]
                        flag = True

                    # If not match record into SA level2 then create here
                    elif not sa2_level_id:
                        self._cr.execute('INSERT INTO subject_industrial_area_level2(level1_id,area_type) '
                                         'values (%s,%s) RETURNING id', (sa1_level_id.id, area_type))
                        query2 = self._cr.fetchone()[0]
                        self._cr.execute('INSERT INTO subject_industrial_area_level2_line(level2_id,name,'
                                         'description) values (%s,%s,%s) RETURNING id', (query2, level2, desc))
                        sa2_line_id = self._cr.fetchone()[0]
                        flag = True

                    # Record inserted into SA2 level line
                    elif sa2_level_id:
                        if not sa2_level_line_id:
                            self._cr.execute('INSERT INTO subject_industrial_area_level2_line(level2_id,name,'
                                             'description) values (%s,%s,%s) RETURNING id',
                                             (sa2_level_id.id, level2, desc))
                            sa2_line_id = self._cr.fetchone()[0]
                            flag = True

                    if flag == True:
                        self._cr.execute('INSERT INTO subject_industrial_area_level3(parent_level2_line_id,'
                                         'parent_level1_id,area_type) values (%s,%s,%s) RETURNING id',
                                         (sa2_line_id, sa1_id, area_type))
                        sa3_id = self._cr.fetchone()[0]
                        self._cr.execute('INSERT INTO subject_industrial_area_level3_line(level3_id,name,'
                                         'description) values (%s,%s,%s) RETURNING id', (sa3_id, level3, desc))

                    elif sa2_level_line_id and sa1_level_id and not sa3_level_id:
                        self._cr.execute('INSERT INTO subject_industrial_area_level3(parent_level2_line_id,'
                                         'parent_level1_id,area_type) values (%s,%s,%s) RETURNING id',
                                         (sa2_level_line_id.id, sa1_level_id.id,area_type))
                        sa3_id = self._cr.fetchone()[0]
                        self._cr.execute('INSERT INTO subject_industrial_area_level3_line(level3_id,name,'
                                         'description) values (%s,%s,%s) RETURNING id', (sa3_id, level3, desc))

                    elif sa3_level_id:
                        if not sa3_level_line_id:
                            self._cr.execute('INSERT INTO subject_industrial_area_level3_line(level3_id,name,'
                                             'description) values (%s,%s,%s) RETURNING id', (sa3_level_id.id, level3, desc))
        except Exception as e:
            _logger.info(e)

        return True
# -*- coding: utf-8 -*-

import logging
try:
    from BytesIO import BytesIO
except ImportError:
    from io import BytesIO
import zipfile
from openerp import http
from openerp.http import request
from openerp.addons.web.controllers.main import content_disposition
import ast

_logger = logging.getLogger(__name__)


class Binary(http.Controller):
    @http.route('/web/binary/download_document', type='http', auth="public")
    def download_document(self, tab_id, **kw):
        """
        This controller is use for download all file in a single click.
        :param tab_id: its give all download files ids.
        :param kw: zip file name given.
        :return: download zip file.
        """
        new_tab = ast.literal_eval(tab_id)
        attachment_ids = request.env['ir.attachment'].search(
            [('id', 'in', new_tab[0])])
        file_dict = {}
        for attachment_id in attachment_ids:
            file_store = attachment_id.store_fname
            if file_store:
                file_name = attachment_id.name
                file_path = attachment_id._full_path(file_store)
                file_dict["%s:%s" % (file_store, file_name)] = dict(
                    path=file_path, name=file_name)
        zip_filename = kw.get('zipname', False)
        zip_filename = "%s.zip" % zip_filename
        bitIO = BytesIO()
        zip_file = zipfile.ZipFile(bitIO, "w", zipfile.ZIP_DEFLATED)
        for file_info in file_dict.values():
            zip_file.write(file_info["path"], file_info["name"])
        zip_file.close()
        return request.make_response(bitIO.getvalue(),
                                     headers=[
                                     ('Content-Type',
                                      'application/x-zip-compressed'),
                                     ('Content-Disposition',
                                      content_disposition(zip_filename))])

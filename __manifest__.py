# -*- coding: utf-8 -*-
{
    'name': "Ulatus CS",
    'summary': """Ulatus CS""",
    'description': """""",
    'author': "Crimson Interactive",
    'website': "https://www.crimsoni.com/",
    'category': "Ulatus CS",
    'version': "11.0.1.0.0",
    # any module necessary for this one to work correctly
    'depends': [
        'base', 'sale', 'sale_management', 'payment',
        'base_address_city', 'datepicker_disable_past_dates',
        'contacts', 'hr', 'product', 'mail', 'sales_team', 'web',
        'web_widget_url_advanced',
        'fine_uploader', 'dynamic_mail'
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/ulatus_security.xml',
        'data/mail_template.xml',
        'data/remainder_template.xml',
        'data/product_data.xml',
        'data/user_data_inherit.xml',
        'data/ir_cron.xml',
        'wizard/quotation_details_wizard_view.xml',
        'wizard/assign_to_others_wiz_view.xml',
        'wizard/confirmation_message_wiz_view.xml',
        'wizard/update_service_level_wiz_view.xml',
        'wizard/mail_compose_message_view.xml',
        'wizard/file_revision_request_wiz_view.xml',
        'wizard/update_po.xml',
        'wizard/update_end_client_wiz.xml',
        'views/menu_view.xml',
        'wizard/data_import_wiz_view.xml',
        'views/working_hours.xml',
        'views/product_master_view.xml',
        'views/addons_service_master_view.xml',
        'views/master_view.xml',
        'views/client_inquiry_view.xml',
        'views/sale_order_view.xml',
        'views/quotation_revision_request_view.xml',
        'views/quotation_pending_for_confirmation_view.xml',
        'views/pm_asn_order_view.xml',
        'views/res_partner_view.xml',
        'views/res_lang_view.xml',
        'views/client_query_view.xml',
        'views/ulatus_config_setting_view.xml',
        'views/all_assignment_view.xml',
        'views/script_view.xml',
        'views/sequence_view.xml',
        'views/all_inquiries_n_quote.xml',
        'views/res_users_view.xml',
        'views/reject_inquiry_view.xml',
        'views/reject_quotation_view.xml',
        'wizard/data_import_wiz_view.xml',
        'wizard/legacy_data_import.xml',
        'wizard/import_masters_wiz.xml',
        'wizard/import_zero_inv_for_adjust.xml',
        'wizard/create_monthly_invoice.xml',
        'wizard/bulk_po_update.xml',
        'views/bi_daily_report.xml',
        # 'views/menu_view.xml',
        'views/account_invoice.xml',
        # 'views/assignment_wiz.xml',
        # 'views/revision_asn_view.xml',
        # 'reports/report_invoice_temp.xml',
        # 'reports/invoice_template_view.xml',
    ],
    'qweb': [
        'static/src/xml/hide_odoo_bindings.xml',
    ],
    # "external_dependencies":  {
    #     'python': ['business-duration']
    # },
}

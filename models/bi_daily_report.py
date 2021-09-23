from odoo import api, fields, models
from datetime import date, datetime


class BIDailyReport(models.Model):
    _name = 'bi.daily.report'
    # _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = 'BI Daily Report'
    _rec_name = 'inquiry_id'

    inquiry_id = fields.Many2one('sale.order', string='Inquiry Number')
    quote_id = fields.Many2one('sale.order', string='Quotation Number')
    parent_asn_id = fields.Many2one('sale.order', string='ASN Number')
    asn_id = fields.Many2one('assignment', string='ASN Number')
    website_name = fields.Char(string='Website Name', default='Global')
    is_rr_inquiry = fields.Char(string='Is RR Inquiry', default='No')
    inquiry_number = fields.Char(string='Inquiry Number', store=True, related='inquiry_id.name')
    asn_number = fields.Char(string='ASN Number')
    assignment_current_status = fields.Char(string='Current Status of ASN')
    is_parent_or_child = fields.Char(string='Is Parent Or Child', default='')

    # Inquiry Fields
    inquiry_date = fields.Datetime("Inquiry Create Date")
    inquiry_state = fields.Selection(
        [('un_assign', 'Unassigned'), ('assign', 'Assigned'),
         ('process', 'Processed')], 'Inquiry State', default='un_assign',
        store=True, related='inquiry_id.inquiry_state')
    mem_id = fields.Char(string='Client MEM ID', store=True, related='inquiry_id.mem_id.name')
    client_name = fields.Char(string='Client Name', store=True, related='inquiry_id.partner_id.name')
    target_lang_ids = fields.Many2many('res.lang', 'res_lang_bi_report_rel', 'bi_report_id', 'res_lang_id', string = 'Target language')
    service = fields.Char(string='Service', default='')
    client_deadline = fields.Datetime(string='Client Deadline')
    currency_id = fields.Char(string='Currency')
    client_type = fields.Char(string='Client Type')

    # Quotation Fields
    area_type = fields.Selection([('subject_area', 'Subject Area'),
                                  ('industrial_area', 'Industrial Area')], string='Area Type', store=True, related='quote_id.area_type')
    subject_industrial_area_level1_id = fields.Char(string="Level 1", store=True, related='quote_id.subject_industrial_area_level1_id.name')
    subject_industrial_area_level2_id = fields.Char(string="Level 2", store=True, related='quote_id.subject_industrial_area_level2_id.name')
    subject_industrial_area_level3_id = fields.Char(string="Level 3", store=True, related='quote_id.subject_industrial_area_level3_id.name')
    level3_other_area = fields.Char(string="Others", store=True, related='quote_id.level3_other_area')
    mark_as_special = fields.Boolean(string='Mark as Special', store=True, related='quote_id.mark_as_special')
    quotataion_sent_by = fields.Char(string='Quotataion Sent By', store=True, related='quote_id.user_id.name')
    actual_client_deadline = fields.Datetime(string='Actual Client Deadline')
    internal_client_deadline = fields.Datetime(string='Internal Client Deadline')
    quote_state = fields.Selection([('draft', 'New Quotation'),
                                    ('sent', 'Quotation Sent'),
                                    ('revision_request', 'Revision Requested'),
                                    ('revise', 'Revised'),
                                    ('on-hold', 'ASN On-Hold'),
                                    ('sale', 'ASN confirmed'),
                                    ('asn_work_in_progress', 'ASN Work-in-progress'),
                                    ('done', 'ASN Completed'),
                                    ('cancel', 'Rejected')],
                                   'Quote Status', store=True, related='quote_id.state')
    response_time = fields.Char(string='Response Time', default='')

    # ASN Fields
    service_level_id = fields.Char(string='Translation Level', store=True, related='parent_asn_id.service_level_id.name')
    priority = fields.Selection([('standard', 'Standard'),
                                 ('express', 'Express'),
                                 ('super_express', 'Super Express')], string='Priority', store=True, related='parent_asn_id.priority')
    unit_id = fields.Char(string='Unit', store=True, related='parent_asn_id.unit_id.name')
    char_count = fields.Integer(string='Unit Count')
    asn_state = fields.Selection([('draft', 'New Quotation'),
                              ('sent', 'Quotation Sent'),
                              ('revision_request', 'Revision Requested'),
                              ('revise', 'Revised'),
                              ('on-hold', 'ASN On-Hold'),
                              ('sale', 'ASN confirmed'),
                              ('asn_work_in_progress', 'ASN Work-in-progress'),
                              ('done', 'ASN Completed'),
                              ('cancel', 'Rejected'),
                              ('new', 'ASN Work-in-progress'),
                              ('revised', 'Revised Assignments'),
                              ('pending', 'Pending For Delivery'),
                              ('deliver', 'Delivered')],
                             'ASN Status')
    gross_fee = fields.Float(string='Gross Fee')
    premium_percentage = fields.Float(string='Premium Percentage')
    premium_amount = fields.Float(string='Premium Amount')
    discount_percentage = fields.Float(string='Sale Universal Discount')
    discount_amount = fields.Float(string='Discount Amount')
    total_tax_percentage = fields.Float(string='Total Tax Percentage')
    total_tax = fields.Float(string='Total Tax')
    total_fees = fields.Float(string='Total Fee')
    quote_confirmation_date = fields.Datetime(string='Quotation confirmation')
    asn_delivery_date = fields.Datetime(string='ASN Delivery Date')
    asn_confirmed_by = fields.Char(string='ASN Confirmed By', store=True, related='parent_asn_id.user_id.name')
    reject_reason = fields.Char(string='Rejection Reason')
    reject_date = fields.Datetime(string='Reject Date')
    inv_type = fields.Selection([('mon', 'Monthly'),
                                 ('ind', 'Individual')], string='Invoice Type')
    invoice_create_date = fields.Datetime(string='Invoice Create Date')
    new_client = fields.Char(string="New or Existing Client", default='')
    is_deadline_met = fields.Char(string="Met", default='')
    organisation_name = fields.Char(string="Organisation Name", default='')
    non_editable_count = fields.Float(string='Non-editable Count', default=0.0)
    wc_0_49_percent = fields.Float(string='0%–49%', default=0.0)
    wc_50_74_percent = fields.Float(string='50%–74%', default=0.0)
    wc_75_84_percent = fields.Float(string='75%–84%', default=0.0)
    wc_85_94_percent = fields.Float(string='85%–94%', default=0.0)
    wc_95_99_percent = fields.Float(string='95%–99%', default=0.0)
    wc_100_percent = fields.Float(string='100%', default=0.0)
    wc_101_percent = fields.Float(string='101%', default=0.0)
    repetitions = fields.Float(string='Repetitions', default=0.0)
    machine_translation = fields.Float(string='Machine Translation', default=0.0)
    client_instructions = fields.Text(string='Client Instructions', default='')
    project_management_cost = fields.Float(string="Project Management Cost", default='')
    final_rate = fields.Float(string="Final Rate", default='')
    po_number = fields.Char(string="Client PO#", default='')
    audio_video_synchronization = fields.Float(string="Audio-Video Synchronization", default='')
    book_editing = fields.Float(string="Book Editing", default='')
    book_indexing = fields.Float(string="Book Indexing", default='')
    consecutive_interpretation = fields.Float(string="Consecutive Interpretation", default='')
    content_extraction = fields.Float(string="Content Extraction", default='')
    cover_designing = fields.Float(string="Cover Designing", default='')
    cross_check = fields.Float(string="CrossCheck", default='')
    dtp_Engineering = fields.Float(string="DTP/Engineering", default='')
    doctors_incentives = fields.Float(string="Doctors Incentives", default='')
    double_back_translation = fields.Float(string="Double Back Translation", default='')
    dubbing = fields.Float(string="Dubbing", default='')
    ebook_generation = fields.Float(string="Ebook Generation", default='')
    embedding_subtitles_video_audio_files = fields.Float(string="Embedding Subtitles in the video/audio files", default='')
    engineering = fields.Float(string="Engineering", default='')
    formatting_artwork_editing = fields.Float(string="Formatting and Artwork Editing", default='')
    frame_maker_formatting = fields.Float(string="Frame Maker Formatting", default='')
    functional_testing = fields.Float(string="Functional Testing", default='')
    glossary_development = fields.Float(string="Glossary development", default='')
    graphic_illustration = fields.Float(string="Graphic Illustration", default='')
    human_voiceover = fields.Float(string="Human Voiceover", default='')
    image_localization = fields.Float(string="Image Localization", default='')
    image_recreation = fields.Float(string="Image Recreation", default='')
    in_context_preview_linguistic_testing = fields.Float(string="In context preview / Linguistic Testing", default='')
    indesign_framework_ai = fields.Float(string="Indesign/Framework/AI Same As Original Formatting", default='')
    interview_recording = fields.Float(string="Interview Recording", default='')
    interviewer_moderation = fields.Float(string="Interviewer/Moderation", default='')
    journal_selection = fields.Float(string="Journal Selection", default='')
    journal_submission = fields.Float(string="Journal Submission", default='')
    lms_synchronization = fields.Float(string="LMS Synchronization", default='')
    lso_lqa = fields.Float(string="LSO / LQA", default='')
    mtpe = fields.Float(string="MTPE", default='')
    machine_voiceover = fields.Float(string="Machine Voiceover", default='')
    multilingual_seo = fields.Float(string="Multilingual SEO", default='')
    only_review_proofreading = fields.Float(string="Only Review / Proofreading", default='')
    pdf_formatting = fields.Float(string="PDF Formatting", default='')
    plagiarism_check = fields.Float(string="Plagiarism Check", default='')
    pre_submission_peer_review = fields.Float(string="Pre-submission Peer Review", default='')
    recruitment_selection = fields.Float(string="Recruitment/Selection of Doctors", default='')
    revised_rejected_paper_editing = fields.Float(string="Revised/ Rejected Paper Editing", default='')
    simultaneous_interpretation = fields.Float(string="Simultaneous Interpretation", default='')
    single_back_translation = fields.Float(string="Single Back Translation", default='')
    style_guide_development = fields.Float(string="Style Guide Development", default='')
    subtitling_closed_caption = fields.Float(string="Subtitling - Closed Caption", default='')
    subtitling_open_caption = fields.Float(string="Subtitling - Open Caption", default='')
    tvt = fields.Float(string="TVT", default='')
    template_creation = fields.Float(string="Template Creation", default='')
    transcription_proofreading = fields.Float(string="Transcription + Proofreading", default='')
    transcription_english_report = fields.Float(string="Transcription / English Report", default='')
    translation_proxy = fields.Float(string="Translation Proxy", default='')
    typesetting = fields.Float(string="Typesetting", default='')
    video_editing = fields.Float(string="Video Editing", default='')
    word_ppt_excel_original_formatting = fields.Float(string="Word/PPT/Excel Same As Original Formatting", default='')
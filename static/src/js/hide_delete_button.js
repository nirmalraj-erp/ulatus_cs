odoo.define('ulatus_cs.HideDeleteButton', function (require) {
"use strict";

var ListRenderer = require("web.ListRenderer");

ListRenderer.include({
    _renderRow: function (record, index) {
            var self = this;
            var $row = this._super.apply(this, arguments)

            // Quoation Instruction Optional Line
            if(record.model === "sale.instruction.line"){
//                if(record.data && 'is_original_ins' in record.data && record.data.is_original_ins){
                if((record.data && 'is_original_ins' in record.data && record.data.is_original_ins) ||
                    (record.data && 'is_default_ins' in record.data && record.data.is_default_ins)){
                    $($row).find('td.o_list_record_delete').removeClass('o_list_record_delete');
                    $($row).find('button[name="delete"]').remove();
                }
            }

            // child assignment Instruction Optional Line
            if(record.model === "assignment.instruction.line"){
//                if(record.data && 'is_original_ins' in record.data && record.data.is_original_ins){
                if((record.data && 'is_original_ins' in record.data && record.data.is_original_ins) ||
                (record.data && 'is_default_ins' in record.data && record.data.is_default_ins)){
                    $($row).find('td.o_list_record_delete').removeClass('o_list_record_delete');
                    $($row).find('button[name="delete"]').remove();
                }
            }

            // Quotation Translation level Line
            if(record.model === "service.level.line"){
                if(record.data && 'is_original_service_level' in record.data && record.data.is_original_service_level){
                    $($row).find('td.o_list_record_delete').removeClass('o_list_record_delete');
                    $($row).find('button[name="delete"]').remove();
                }
            }

            return $row
        },

})
});
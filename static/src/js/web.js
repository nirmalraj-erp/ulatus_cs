odoo.define('custom.basic_fields', function (require) {
"use strict";
    var basic_fields = require('web.basic_fields');
    var registry = require('web.field_registry');

    var CustomBinaryField = basic_fields.FieldBinaryFile.extend({
        _render: function (){
            this._super.apply(this, arguments);
            if (this.value) {
                this.$('button.o_clear_file_button').addClass('o_hidden');
            }
        },
    });
    registry.add('custom_binary_field', CustomBinaryField)
})
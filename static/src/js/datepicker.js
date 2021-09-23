odoo.define('ulatus_cs.datepicker', function(require) {
"use strict";

    var Widget = require('web.datepicker');
    var time = require('web.time');

    Widget.DateWidget.include({

//        Override : To restrict multiple time execution of Onchange for datetime field
        changeDatetime: function () {
            if (this.__libInput > 0) {
                if (this.options.warn_future) {
                    this._warnFuture(this.getValue());
                }
                return;
            }
            var oldValue = this.getValue();
            if (this.isValid()) {
                this._setValueFromUi();
                var newValue = this.getValue();
                var hasChanged = !oldValue !== !newValue;
                if (oldValue && newValue) {
                    var formattedOldValue = oldValue.format(time.getLangDatetimeFormat());
                    var formattedNewValue = newValue.format(time.getLangDatetimeFormat());
                    if (formattedNewValue !== formattedOldValue) {
                        hasChanged = true;
                    }
                }
                if (hasChanged) {
                    if (this.options.warn_future) {
                        this._warnFuture(newValue);
                    }
                    this.trigger("datetime_changed");
                }
            } else {
                var formattedValue = oldValue ? this._formatClient(oldValue) : null;
                this.$input.val(formattedValue);
            }
        },

    });

});

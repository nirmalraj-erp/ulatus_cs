odoo.define('ulatus_cs.field_controller', function (require) {
"use strict";

    var BasicController = require('web.BasicController');
    var view_dialogs = require('web.view_dialogs');
    var Dialog = require('web.Dialog');
    var core = require('web.core');
    var _t = core._t;

    view_dialogs.FormViewDialog.include({
    	init: function (parent, options) {
        var self = this;

        this.res_id = options.res_id || null;
        this.on_saved = options.on_saved || (function () {});
        this.context = options.context;
        this.model = options.model;
        this.parentID = options.parentID;
        this.recordID = options.recordID;
        this.shouldSaveLocally = options.shouldSaveLocally;

        var multi_select = !_.isNumber(options.res_id) && !options.disable_multiple_selection;
//        console.log("multi_select",multi_select,this,options.res_model);
        var readonly = _.isNumber(options.res_id) && options.readonly;

        if (!options || !options.buttons) {
            options = options || {};
            options.buttons = [{
                text: (readonly ? _t("Close") : _t("Discard")),
                classes: "btn-default o_form_button_cancel",
                close: true,
                click: function () {
                    if (!readonly) {
                        self.form_view.model.discardChanges(self.form_view.handle, {
                            rollback: self.shouldSaveLocally,
                        });
                    }
                },
            }];

            if (!readonly) {
                options.buttons.unshift({
                    text: _t("Save") + ((multi_select)? " " + _t(" & Close") : ""),
                    classes: "btn-primary",
                    click: function () {
                        this._save().then(self.close.bind(self));
                    }
                });
                if(options.res_model != 'sale.order.line' ){
                    if (multi_select) {
                        options.buttons.splice(1, 0, {
                            text: _t("Save & New"),
                            classes: "btn-primary",
                            click: function () {
                                this._save().then(self.form_view.createRecord.bind(self.form_view, self.parentID));
                            },
                        });
                    }
                }
            }
        }
        this._super(parent, options);
    },

    });
 });
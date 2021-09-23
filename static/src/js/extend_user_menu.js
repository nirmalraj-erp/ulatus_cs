odoo.define('ulatus_cs.ExtendUserMenu', function (require) {
"use strict";

/**
 * This widget is appended by the UserMenu to the right of the navbar.
 * Included the new change Password Functionality to the Old Menu.
 * If clicked, it opens a dropdown allowing the user to perform actions like
 * Change Password and Logout.
 */

var UserMenu = require('web.UserMenu');

var IncludeUserMenu = UserMenu.include({
    _onMenuPassword_change: function () {
        var self = this;
        var session = this.getSession();
        this.trigger_up('clear_uncommitted_changes', {
            callback: function () {
                self.do_action({
                    'type': 'ir.actions.client',
                    'tag': 'change_password',
                    'target': 'new',
                });
            },
        });
    },
});

return IncludeUserMenu;

});
$(document).ready(function() {
    var editor = new $.fn.dataTable.Editor({
        ajax: {
            create: {
                type: 'POST',
                url:  '/account'
            },
            edit: {
                type: 'PUT',
                url:  '/account?id=_id_'
            },
            remove: {
                type: 'DELETE',
                url:  '/account?id=_id_'
            }
        },
        table: "#dt_account",
        fields: [
            {
                label: "Google ID:",
                name: "uid"
            }, {
                label: "Password:",
                name: "passwd",
                type: "password"
            }, {
                label: "Android ID:",
                name: "device_id"
            }, {
                label: "Account Type:",
                name: "account_type",
                type: "select",
                options: [
                    { label: "Free", value: 1 },
                    { label: "Paid", value: 2 }
                ]
            }, {
                label: "Android Version:",
                name: "system_version"
            }, {
                label: "Status:",
                name: "is_deleted",
                type: "radio",
                options: [
                    { label: "Active", value: 0 },
                    { label: "Inactive", value: 1 }
                ]
            }
        ]
    });

    $('#dt_account').DataTable({
        dom: "Bfrtip",
        responsive: true,
        ajax: "/account",
        columns: [
            { data: "uid" },
            { data: "device_id" },
            { data: "system_version" },
            {
                data: "account_type",
                render: function( data, type, row ) {
                    return data == 1 ? "Free" : "Paid";
                }
            },
            {
                data: "is_deleted",
                render: function( data, type, row) {
                    return data ? "Inactive" : "Active";
                }
            }
        ],
        select: true,
        buttons: [
            { extend: "create", editor: editor },
            { extend: "edit",   editor: editor },
            { extend: "remove", editor: editor }
        ]
    });
});

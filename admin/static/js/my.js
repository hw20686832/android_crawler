$(document).ready(function() {
    $.extend($.fn.dataTable.defaults, {
        'searching': false,
        "language": {
            'processing': 'loading...',
            'infoEmpty': '...',
            'emptyTable': '',
            'paginate': {
                'first': '<<',
                'previous': '<',
                'next': '>',
                'last': '>>'}
        }
    });

    var editor = new $.fn.dataTable.Editor({
        ajax: {
            create: {
                type: 'POST',
                url:  '/rlist'
            },
            remove: {
                type: 'DELETE',
                url: '/rlist?id=_id_'
            }
        },
        table: "#main_table_ready",
        fields: [
            {
                label: "Package Name:",
                name: "appid"
            },
        ]
    });

    var dt_ready = $('#main_table_ready').dataTable({
        dom: "Bfrtip",
        serverSide: true,
        responsive: true,
        stateSave: true,
        ordering: false,
        select: true,
        ajax: {
            "url": "/rlist"
        },
        columns: [
            { data: "appid" },
            { data: "price" },
            { data: "create_time" },
        ],
        buttons: [
            { extend: "create", editor: editor },
            { extend: "remove", editor: editor },
            {
                text: 'Grab',
                extend: 'remove',
                action: function ( e, dt, node, conf ) {
                    var selected_rows = dt.rows( { selected: true } );
                    $.post(
                        '/schd',
                        {
                            'config': dt.button( 3 ).text(),
                            'ids': selected_rows.ids().join(',')
                        }
                    ).done(function(data) {
                        selected_rows.remove().draw(false);
                    });
                }
            },
            {
                extend: 'collection',
                text: 'Select Google ID',
                autoClose: true,
                fade: true,
                buttons: function(api, btn) {
                    var btns = Array();
                    $.ajax({
                        url: '/profile',
                        method: 'GET',
                        async: false,
                        success: function(data) {
                            $.each(data, function(name, item) {
                                var btn = {
                                    text: item['uid'],
                                    action: function( e, dt, button, config ) {
                                        dt.button( 3 ).text(item['uid']);
                                    }
                                };
                                btns.push(btn);
                            });
                            if (btns.length > 0) {
                                api.button( 3 ).text(btns[0].text);
                            }
                        }
                    });
                    return btns;
                }
            }
        ]
    });

    var dt_download = $('#main_table_download').dataTable({
        serverSide: true,
        responsive: true,
        ordering: false,
        paging: false,
        ajax: {
            "url": "/dqueue"
        },
        columns: [
            {'data': 'appid'},
            {'data': 'uid'},
            {'data': 'start_time'},
            {'data': 'status'}
        ]
    });

    var interval = null;
    $("#download_tab").on("show.bs.tab", function() {
        interval = setInterval(function() {
            dt_download.api().ajax.reload(null, false);
        }, 5000);
    }).on("hide.bs.tab", function() {
        clearInterval(interval);
    });

    var dt_paid = $('#main_table_paid').dataTable({
        serverSide: true,
        responsive: true,
        processing: true,
        ordering: false,
        searching: true,
        ajax: {
            url: "/paidlist"
        },
        columns: [
            {'data': 'appid'},
            {'data': 'name'},
            {'data': 'uid'},
            {'data': 'price'},
            {'data': 'create_time'},
        ]
    });

    var interval_paid = null;
    $("#paid_tab").on("show.bs.tab", function() {
        interval_paid = setInterval(function() {
            dt_paid.api().ajax.reload(null, false);
        }, 60000);
    }).on("hide.bs.tab", function() {
        clearInterval(interval_paid);
    });

});

$(document).ready(function() {
    var editor = new $.fn.dataTable.Editor({
        ajax: {
            create: {
                type: 'POST',
                url:  '/blacklist'
            },
            remove: {
                type: 'DELETE',
                url: '/blacklist?id=_id_'
            }
        },
        table: "#dt_blacklist",
        fields: [
            {
                label: "Package Name:",
                name: "appid"
            },
        ]
    });

    $('#dt_blacklist').on( 'click', 'a.remove', function (e) {
        editor
            .title( 'Delete row' )
            .message( 'Are you sure you wish to delete this row?' )
            .buttons( { "label": "Delete", "fn": function () { editor.submit(); } } )
            .remove( $(this).closest('tr') );
    } );

    $('#dt_blacklist').DataTable({
        dom: "Bfrtip",
        responsive: true,
        order: [[ 0, 'desc' ]],
        ajax: "/blacklist",
        columns: [
            { data: "appid" },
            { data: "create_time" },
            {
                data: null,
                defaultContent: '<a href="#" class="remove">Delete</a>',
                orderable: false
            },
        ],
        buttons: [
            {
                extend: "create",
                editor: editor
            },
        ]
    });

    $('#remove_form').on('submit', function(e) {
        var appids = $('#clean_app').val();
        if (appids.trim().length == 0) {
            return false;
        }
        $.ajax({
            "url": "/clean",
            "method": "POST",
            "data": {'appids': $('#clean_app').val()},
            "success": function(data) {
                $('#alert').empty();
                var edt = editor.create( data.length, false );
                var id_field = edt.field( 'appid' );
                for (var i in data) {
                    id_field.multiSet( i, data[i][0] );
                }

                edt.submit(function(result) {
                    for (var n in result.data) {
                        var alert_div = $('#alert-message').append(
                           '<div id="inner-message" class="alert alert-success alert-dismissible fade in" role="alert">' +
                           '    <button type="button" class="close" data-dismiss="alert" aria-label="Close"><span aria-hidden="true">&times;</span></button>' +
                           '    App <strong>' + result.data[n]['appid'] + '</strong> added to blacklist.' +
                           '</div>'
                        );
                        var alert = alert_div[0].lastChild;
                        $(alert).hide();
                        $(alert).alert();
                        $(alert).fadeTo(2000, 500).slideUp(500, function(){
                            $(alert).alert('close');
                        });
                    }
                });
            },
            "dataType": "json",
            "complete": function(xhr, status) {
                $('#remove_form')[0].reset();
            }
        });

        return false;
    });
});

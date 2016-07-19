$(document).ready(function() {
    var date_format = function(date_obj) {
        var month = date_obj.getMonth() + 1;
        month = month < 10 ? '0' + month : month;
        var date = date_obj.getDate();
        date = date < 10 ? '0' + date : date;
        var date_string = date_obj.getFullYear() + '-' + month + '-' + date;
        return date_string;
    };

    $.extend($.fn.dataTable.defaults, {
        "processing": true,
        "language": {
            'processing': 'loading...',
            'infoEmpty': '...',
            'emptyTable': 'No data...',
            'paginate': {
                'first': '<<',
                'previous': '<',
                'next': '>',
                'last': '>>'}
        }
    });

    var full_tb = $('#full_tb').dataTable({
        stateSave: true,
        responsive: true,
        processing: true,
        ordering: false,
        searching: true,
        pageLength: 25,
        ajax: "/crawler?g=full",
        rowCallback: function(row, data) {
            $(row).attr('status', 'show');
            var tag = $($('td', $(row))[3]).html();
            $(row).attr('datatype', tag);
        },
        columns: [
            {'data': 'appid'},
            {'data': 'version_name'},
            {'data': 'group'},
            {'data': 'tag'},
            {'data': 'download'}
        ]
    });

    // Date picker control
    var dp = $('#dp').datepicker(
        {
            format: "yyyy-mm-dd",
            autoclose: true,
            todayHighlight: true,
            startDate: "-7d",
            todayBtn: "linked"
        }
    ).on('changeDate', function() {
        $('#data_type').prop('selectedIndex', 0);
        var cur_date = $(this).datepicker('getDate');
        var date_string = date_format(cur_date);

        full_tb.api().ajax.url("/crawler?g=full&d=" + date_string).load();
    });

    var yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    dp.datepicker('update', yesterday);

    $('#data_type').on("change", function() {
        var api = full_tb.api();
        api.column(3).search(this.value === 'all' ? '' : this.value, true, false).draw();
    });
});

// script.js
function loadData(page) {
    // Correct value for pages
    if (isNaN(page) || page <= 0) {
        page = 1;
    }

    $.get(`/load_data?page=${page}`, function(data) {
        // RESET THE TABLE
        $('#table-body').empty();

        // INSERT NEW DATA
        data.forEach(function(item) {
            $('#table-body').append(`
                <tr>
                    <td>${item.id}</td>
                    <td>${item.contract_address}</td>
                    <td>${item.verified_code}</td>
                    <td>${item.token_usd_total}</td>
                    <td>${item.token_list}</td>
                    <td>${item.source_code}</td>
                    <td>${item.contract_name}</td>
                    <td>${item.contract_usd_balance}</td>
                </tr>
            `);
        });
    });
}

$(document).ready(function() {
    loadData(1);

    $('#pagination').on('click', 'a.page-link', function(event) {
        event.preventDefault();
        // Correct value for data('page')
        let page = parseInt($(this).data('page'));
        if (!isNaN(page) && page > 0) {
            loadData(page);
        }
    });

    $('#prev-page').on('click', function() {
        let currentPage = parseInt($('#pagination .active').text());
        if (currentPage > 1) {
            loadData(currentPage - 1);
        }
    });

    $('#next-page').on('click', function() {
        let currentPage = parseInt($('#pagination .active').text());
        loadData(currentPage + 1);
    });
});

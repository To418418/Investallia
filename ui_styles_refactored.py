# ui_styles.py
import json # JSONを扱うために必要

# --- ポートフォリオ入力ページ用カスタムCSS ---
portfolio_custom_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="st-"], .main .block-container, .stTextInput input, .stNumberInput input, .stTextArea textarea, .stButton button, .stMarkdown, h1, h2, h3, th, td {
        font-family: 'Inter', sans-serif !important;
    }
    .main .block-container {
        max-width: 900px; padding: 2rem; background-color: #FFFFFF;
        border-radius: 0.75rem; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05);
        margin: 1rem auto;
    }
    .stTextInput input, .stNumberInput input, .stTextArea textarea {
        width: 100%; padding: 0.75rem; border: 1px solid #D1D5DB;
        border-radius: 0.375rem; box-sizing: border-box;
    }
    .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
        outline: 2px solid transparent; outline-offset: 2px;
        border-color: #60A5FA !important; box-shadow: 0 0 0 2px #BFDBFE !important;
    }
    .main-title {
        font-size: 2.25rem; font-weight: bold; text-align: center;
        margin-bottom: 2rem; color: #1F2937;
    }
    .section-title {
        font-size: 1.5rem; font-weight: 600; margin-top: 1.5rem;
        margin-bottom: 1rem; color: #1F2937; border-bottom: 1px solid #e5e7eb;
        padding-bottom: 0.5rem;
    }
    .stDataFrame th {
        background-color: #F3F4F6; padding: 0.75rem; text-align: left;
        font-weight: 600; color: #374151;
    }
    .result-box {
        background-color: #F3F4F6; padding: 1rem; border-radius: 0.375rem;
        margin-top: 2rem; border: 1px solid #E5E7EB;
    }
    .result-box h3 {
        font-size: 1.25rem; font-weight: 600; margin-bottom: 0.5rem; color: #1F2937;
    }
    .result-box pre {
        white-space: pre-wrap; word-wrap: break-word; font-size: 0.875rem;
        background-color: transparent !important;
    }
    div[data-testid="stButton"] > button {
        background-color: #10B981; color: white; padding: 0.6rem 1.2rem;
        border-radius: 0.375rem; font-weight: 600; transition: background-color 0.3s;
        font-size: 1rem; border: none;
    }
    div[data-testid="stButton"] > button:hover { background-color: #059669; color: white; }
    div[data-testid="stButton"] > button:active { background-color: #047857; }
    div[data-testid="stButton"] > button:focus {
        outline: 2px solid transparent; outline-offset: 2px; box-shadow: 0 0 0 2px #059669;
    }
    .submit-button-container { text-align: center; margin-top: 2rem; }
    .navigation-buttons-container { display: flex; justify-content: space-between; margin-top: 2rem; }
</style>
"""

trade_history_page_style = """
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .trade-history-content-wrapper {
            background-color: white; padding: 1.5rem; border-radius: 0.5rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
            margin-bottom: 1rem;
        }
        h1.app-title-trade {
            font-size: 1.875rem; font-weight: 700; color: #334155; margin-bottom: 0.5rem;
        }
        p.app-subtitle-trade { color: #475569; margin-bottom: 1.5rem; }
        h2.section-title-trade { font-size: 1.25rem; font-weight: 600; color: #334155; }
        .pagination-controls .stButton>button { margin-left: 0.25rem; margin-right: 0.25rem; }
    </style>
</head>
"""

def generate_stock_report_html(options_html, js_data_string):
    # JavaScript文字列内の特殊文字をエスケープ
    # \ -> \\, ` -> \`, ${ -> \${
    escaped_js_data_string = js_data_string.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
    # f-string を使わずに文字列結合
    html_parts = [
        "<!DOCTYPE html><html lang=\"ja\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
        "<title>株式情報レポート</title>",
        "<script src=\"https://cdn.tailwindcss.com\"></script>",
        "<script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>",
        "<script src=\"https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns\"></script>",
        "<link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap\" rel=\"stylesheet\">",
        "<style>body { font-family: 'Inter', sans-serif; background-color: #f3f4f6; } .card { background-color: white; border-radius: 0.75rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1); padding: 1.5rem; margin-bottom: 1.5rem; } .section-title { font-size: 1.25rem; font-weight: 600; color: #1f2937; margin-bottom: 1rem; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.5rem; } .news-item { border-bottom: 1px solid #e5e7eb; padding-bottom: 0.75rem; margin-bottom: 0.75rem; } .news-item:last-child { border-bottom: none; margin-bottom: 0; } .news-title-link { color: #1f2937; text-decoration: none; } .news-title-link:hover { color: #4f46e5; text-decoration: underline; } .stat-item { display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px dashed #e5e7eb; } .stat-item:last-child { border-bottom: none; } .stat-label { color: #4b5563; } .stat-value { font-weight: 500; color: #1f2937; } .disclaimer { font-size: 0.75rem; color: #6b7280; text-align: center; padding: 1rem; margin-top: 1.5rem; } @media (max-width: 768px) { .main-grid { grid-template-columns: 1fr; } .header-content { flex-direction: column; align-items: center; } .header-content img { margin-top: 1rem; } } table { border-collapse: collapse; width: 100%; } th, td { padding: 0.5rem; text-align: left; word-break: break-word; } thead th { background-color: #f9fafb; } tbody tr:nth-child(even) { background-color: #f9fafb; } #recommendations-table-transposed th:not(:first-child) { text-align: center; } #recommendations-table-transposed td:not(:first-child) { text-align: center; } #recommendations-table-transposed td:first-child { font-weight: 600; } </style></head>",
        "<body class=\"p-4 md:p-8\"><div class=\"max-w-6xl mx-auto\">",
        "<div class=\"mb-6\"><label for=\"stock-select\" class=\"block text-sm font-medium text-gray-700 mb-1\">銘柄選択:</label>",
        "<select id=\"stock-select\" class=\"w-full md:w-1/3 p-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500\">",
        options_html,
        "</select></div><div id=\"stock-details-container\"></div>",
        "<div class=\"disclaimer\">免責事項: 表示される情報は投資助言を目的としたものではなく、またその正確性や完全性を保証するものではありません。投資に関する最終決定はご自身の判断でお願いします。</div></div>",
        "<script> console.log(\"Stock Report Script Loaded\"); Chart.defaults.font.family = \"'Inter', sans-serif\"; let stockDataFromPython; try { stockDataFromPython = JSON.parse(`",
        escaped_js_data_string,
        "`); console.log(\"Parsed stockDataFromPython:\", JSON.parse(JSON.stringify(stockDataFromPython))); } catch (e) { console.error(\"Error parsing stockDataFromPython:\", e); document.getElementById('stock-details-container').innerHTML = '<p class=\"text-red-500\">銘柄データの解析に失敗しました。コンソールを確認してください。</p>'; stockDataFromPython = {}; } let currentStockChart = null; let currentFinancialSummaryChart = null; function renderStockDetails(stockCode) { console.log(\"Attempting to render details for stock code:\", stockCode); const data = stockDataFromPython[stockCode]; console.log(\"Data for stock code \" + stockCode + \":\", JSON.parse(JSON.stringify(data))); if (!data) { console.error(\"No data found for stock code:\", stockCode); document.getElementById('stock-details-container').innerHTML = '<p class=\"text-red-500\">銘柄データが見つかりません（コード: ' + stockCode + '）。</p>'; return; } const financialsHtml = data.financials && Array.isArray(data.financials) ? data.financials.map(item => `<div class=\"stat-item\"><span class=\"stat-label\">${item.label || 'N/A'}:</span><span class=\"stat-value\">${item.value !== undefined && item.value !== null ? String(item.value) : 'N/A'}</span></div>`).join('') : '<p class=\"text-sm text-gray-500\">主要財務指標データなし</p>'; const newsHtml = data.news && Array.isArray(data.news) ? data.news.map(item => `<div class=\"news-item\"><p class=\"text-sm text-gray-500\">${item.date || 'N/A'} - ${item.source || 'N/A'}</p><a href=\"${item.url || '#'}\" target=\"_blank\" rel=\"noopener noreferrer\" class=\"news-title-link font-medium\">${item.title || 'N/A'}</a></div>`).join('') : '<p class=\"text-sm text-gray-500\">ニュースデータなし</p>'; const today = new Date(); const displayDate = `${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日`; const currentPriceDisplay = (data.currentPrice !== undefined && data.currentPrice !== null) ? data.currentPrice.toLocaleString() + '円' : 'N/A'; const detailsHtml = `<div class=\"card\"><div class=\"flex flex-col md:flex-row justify-between items-start md:items-center mb-4 header-content\"><div><h2 class=\"text-2xl font-bold text-indigo-700\">${data.companyName || 'N/A'} (${data.ticker || 'N/A'})</h2><p class=\"text-3xl font-bold text-gray-900 mt-1\">${currentPriceDisplay}<span class=\"${data.priceChangeColor || 'text-gray-500'} text-lg font-medium\">${data.priceChange || 'N/A'}</span></p><p class=\"text-sm text-gray-500\">取得日時: ${displayDate} (データは遅延の可能性あり)</p></div><img src=\"${data.logo_url || 'https://placehold.co/120x60/e0e7ff/3730a3?text=Logo'}\" alt=\"${data.companyName || 'N/A'} ロゴ\" class=\"rounded mt-4 md:mt-0 h-16 object-contain\" onerror=\"this.src='https://placehold.co/120x60/e0e7ff/3730a3?text=Logo'; this.onerror=null;\"></div></div><div class=\"grid grid-cols-1 md:grid-cols-3 gap-6 main-grid\"><div class=\"md:col-span-2\"><div class=\"card\"><h3 class=\"section-title\">株価チャート (過去1年・月足)</h3><div style=\"height: 300px;\"><canvas id=\"stockChartCanvas\"></canvas></div></div><div class=\"card\"><h3 class=\"section-title\">業績サマリー (通期・億円単位)</h3>${data.financialSummaryAnnual && data.financialSummaryAnnual.table_html ? data.financialSummaryAnnual.table_html : '<p class=\"text-sm text-gray-500\">通期業績サマリーデータなし</p>'}<h3 class=\"section-title mt-6\">業績グラフ (通期 売上高・純利益)</h3><div style=\"height: 300px;\"><canvas id=\"financialSummaryChartCanvas\"></canvas></div></div><div class=\"card\"><h3 class=\"section-title\">業績サマリー (四半期・億円単位)</h3>${data.financialSummaryQuarterly && data.financialSummaryQuarterly.table_html ? data.financialSummaryQuarterly.table_html : '<p class=\"text-sm text-gray-500\">四半期業績サマリーデータなし</p>'}</div></div><div class=\"md:col-span-1\"><div class=\"card\"><h3 class=\"section-title\">主要財務指標</h3><div id=\"financials-list\">${financialsHtml}</div></div><div class=\"card\"><h3 class=\"section-title\">関連ニュース</h3><div id=\"news-list\">${newsHtml}</div></div><div class=\"card\"><h3 class=\"section-title\">決算発表日</h3>${data.earningsDatesHtml || '<p class=\"text-sm text-gray-500\">決算発表日データなし</p>'}</div><div class=\"card\"><h3 class=\"section-title\">アナリスト推奨</h3>${data.recommendationsHtml || '<p class=\"text-sm text-gray-500\">アナリスト推奨データなし</p>'}</div></div></div>`; document.getElementById('stock-details-container').innerHTML = detailsHtml; try { console.log(\"Attempting to render stock chart. Historical prices:\", JSON.parse(JSON.stringify(data.historicalPrices))); if (currentStockChart) currentStockChart.destroy(); const stockCtx = document.getElementById('stockChartCanvas')?.getContext('2d'); if (stockCtx && data.historicalPrices && Array.isArray(data.historicalPrices.labels) && data.historicalPrices.labels.length > 0 && Array.isArray(data.historicalPrices.data) && data.historicalPrices.data.some(d => d !== null)) { console.log(\"Stock Chart - Labels:\", data.historicalPrices.labels, \"Data:\", data.historicalPrices.data); currentStockChart = new Chart(stockCtx, { type: 'line', data: { labels: data.historicalPrices.labels, datasets: [{ label: '株価 (円)', data: data.historicalPrices.data, borderColor: '#4f46e5', backgroundColor: 'rgba(79,70,229,0.1)', tension: 0.1, fill: true, pointRadius: 3, pointBackgroundColor: '#4f46e5', spanGaps: true }] }, options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: false, ticks: { callback: value => value.toLocaleString() + '円' } }, x: { grid: { display: false } } }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => `${ctx.dataset.label || ''}: ${ctx.parsed.y !== null ? ctx.parsed.y.toLocaleString() : 'N/A'}円` } } } } }); console.log(\"Stock chart rendered.\"); } else if (stockCtx) { console.warn(\"Stock Chart: No valid data or canvas context for stock chart.\", JSON.parse(JSON.stringify(data.historicalPrices))); stockCtx.clearRect(0, 0, stockCtx.canvas.width, stockCtx.canvas.height); stockCtx.textAlign = 'center'; stockCtx.textBaseline = 'middle'; stockCtx.fillStyle = '#6b7280'; stockCtx.fillText('株価チャートデータを取得できませんでした。', stockCtx.canvas.width / 2, stockCtx.canvas.height / 2); } else { console.error(\"Stock chart canvas context not found.\"); } } catch (e) { console.error(\"Error rendering stock chart:\", e, JSON.parse(JSON.stringify(data.historicalPrices))); } try { console.log(\"Attempting to render financial summary chart. Chart data:\", JSON.parse(JSON.stringify(data.financialSummaryChart))); if (currentFinancialSummaryChart) currentFinancialSummaryChart.destroy(); const summaryCtx = document.getElementById('financialSummaryChartCanvas')?.getContext('2d'); if (summaryCtx && data.financialSummaryChart && Array.isArray(data.financialSummaryChart.labels) && data.financialSummaryChart.labels.length > 0 && Array.isArray(data.financialSummaryChart.datasets) && data.financialSummaryChart.datasets.length > 0) { let allDatasetsHaveSomeData = data.financialSummaryChart.datasets.every(ds => ds.data && Array.isArray(ds.data) && ds.data.some(d => d !== null)); console.log(\"Financial Summary Chart - Labels:\", data.financialSummaryChart.labels, \"Datasets:\", JSON.parse(JSON.stringify(data.financialSummaryChart.datasets)), \"All datasets have data:\", allDatasetsHaveSomeData); if(allDatasetsHaveSomeData){ currentFinancialSummaryChart = new Chart(summaryCtx, { type: 'bar', data: data.financialSummaryChart, options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { callback: value => value.toLocaleString() + '億円' } }, x: { grid: { display: false } } }, plugins: { legend: { position: 'top' }, tooltip: { callbacks: { label: ctx => `${ctx.dataset.label || ''}: ${ctx.parsed.y !== null ? ctx.parsed.y.toLocaleString() : 'N/A'}億円` } } } } }); console.log(\"Financial summary chart rendered.\"); } else { console.warn(\"Financial Summary Chart: Not all datasets have valid data.\"); summaryCtx.clearRect(0, 0, summaryCtx.canvas.width, summaryCtx.canvas.height); summaryCtx.textAlign = 'center'; summaryCtx.textBaseline = 'middle'; summaryCtx.fillStyle = '#6b7280'; summaryCtx.fillText('業績グラフのデータセットに有効なデータがありません。', summaryCtx.canvas.width / 2, summaryCtx.canvas.height / 2); } } else if (summaryCtx) { console.warn(\"Financial Summary Chart: No valid data or canvas context for financial summary chart.\", JSON.parse(JSON.stringify(data.financialSummaryChart))); summaryCtx.clearRect(0, 0, summaryCtx.canvas.width, summaryCtx.canvas.height); summaryCtx.textAlign = 'center'; summaryCtx.textBaseline = 'middle'; summaryCtx.fillStyle = '#6b7280'; summaryCtx.fillText('通期業績グラフデータを取得できませんでした。', summaryCtx.canvas.width / 2, summaryCtx.canvas.height / 2); } else { console.error(\"Financial summary chart canvas context not found.\"); } } catch (e) { console.error(\"Error rendering financial summary chart:\", e, JSON.parse(JSON.stringify(data.financialSummaryChart))); } } const stockSelect = document.getElementById('stock-select'); if (stockSelect) { stockSelect.addEventListener('change', function() { renderStockDetails(this.value); }); if (stockSelect.options.length > 0) { console.log(\"Initial render for stock:\", stockSelect.value); renderStockDetails(stockSelect.value); } else { console.warn(\"No stock options available in select dropdown.\"); document.getElementById('stock-details-container').innerHTML = '<p class=\"text-red-500\">表示する銘柄が選択肢にありません。</p>'; } } else { console.error(\"Stock select dropdown not found.\"); const container = document.getElementById('stock-details-container'); if (container) { container.innerHTML = '<p class=\"text-red-500\">銘柄選択のドロップダウンが見つかりません。</p>'; } } </script></body></html>"
    ]
    return "".join(html_parts)


def generate_chat_html(chat_json_from_llm_process: str):
    """
    LLMが生成したチャットデータ (JSON文字列) を受け取り、
    表示用のHTMLを生成します。
    Pythonのf-stringによる展開を避け、安全な文字列結合を使用します。
    """
    # chat_json_from_llm_process は、llm_chat_page.process_chat_data が返したJSON文字列。
    # これをJavaScriptのJSON.parseに渡すために、JSの文字列リテラルとして埋め込む。
    # そのために、Pythonのjson.dumpsでエスケープする。
    js_escaped_json_string = json.dumps(chat_json_from_llm_process)

    # HTMLの各部分をリストとして定義
    html_parts = [
        "<!DOCTYPE html><html lang=\"ja\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
        "<title>LLMチャット</title><script src=\"https://cdn.tailwindcss.com\"></script>",
        "<style> body { font-family: \"Inter\", sans-serif; } </style></head>",
        "<body class=\"bg-slate-100 flex flex-col items-center min-h-screen py-8\">",
        "<div class=\"w-full max-w-md bg-white rounded-lg shadow-xl flex flex-col\">",
        # Header
        "<header class=\"bg-slate-700 text-white p-4 flex items-center justify-between rounded-t-lg sticky top-0 z-10\">",
        "<h1 class=\"text-xl font-semibold\">LLMチャットデモ</h1>",
        "<div class=\"flex space-x-2\">",
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-search\"><circle cx=\"11\" cy=\"11\" r=\"8\"/><path d=\"m21 21-4.3-4.3\"/></svg>",
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-menu\"><line x1=\"4\" x2=\"20\" y1=\"12\" y2=\"12\"/><line x1=\"4\" x2=\"20\" y1=\"6\" y2=\"6\"/><line x1=\"4\" x2=\"20\" y1=\"18\" y2=\"18\"/></svg>",
        "</div></header>",
        # Chat Container
        "<div id=\"chatContainer\" class=\"chat-container flex-grow p-6 space-y-4 bg-slate-200 overflow-y-auto\" style=\"height: 600px;\"></div>",
        # Footer
        "<footer class=\"bg-white p-3 border-t border-slate-300 rounded-b-lg sticky bottom-0 z-10\">",
        "<div class=\"flex items-center space-x-2\">",
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-smile text-slate-500\"><circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"M8 14s1.5 2 4 2 4-2 4-2\"/><line x1=\"9\" x2=\"9.01\" y1=\"9\" y2=\"9\"/><line x1=\"15\" x2=\"15.01\" y1=\"9\" y2=\"9\"/></svg>",
        "<input type=\"text\" placeholder=\"メッセージを入力...\" class=\"flex-grow p-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500\" disabled>",
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"lucide lucide-send text-blue-500 cursor-pointer hover:text-blue-600\"><path d=\"m22 2-7 20-4-9-9-4Z\"/><path d=\"M22 2 11 13\"/></svg>",
        "</div></footer>",
        "</div>", # end of w-full max-w-md
        # Script part
        "<script>\nconst rawJsonString = ",
        js_escaped_json_string, # ここでエスケープ済みのJSON文字列を埋め込む
        ";\n",
        """let chatData = [];
        try {
            chatData = JSON.parse(rawJsonString);
        } catch (e) {
            console.error("Error parsing chatData from rawJsonString:", e, rawJsonString);
            chatData = [{ sender: "システム", message: "チャットデータの解析に失敗しました (JSON.parse段階)。元の文字列: " + rawJsonString, time: "エラー", isCurrentUser: false, icon: "⚠️" }];
        }
        
        const chatContainer = document.getElementById('chatContainer');
        function displayMessages() {
            chatData.forEach(item => {
                const messageWrapper = document.createElement('div');
                messageWrapper.classList.add('flex', 'items-end', 'space-x-2', 'max-w-[85%]');
                
                const messageBubble = document.createElement('div');
                messageBubble.classList.add('p-3', 'rounded-lg', 'shadow');
                
                const senderName = document.createElement('div');
                senderName.classList.add('text-xs', 'text-slate-600', 'mb-1');
                senderName.textContent = item.sender;
                
                const messageText = document.createElement('p');
                messageText.classList.add('text-sm');
                const messageContent = typeof item.message === 'string' ? item.message : String(item.message);
                messageText.innerHTML = messageContent
                    .replace(/\\\\n/g, '<br>') // JSON文字列内のエスケープされた \\n を <br> に (例: '\\\\n' -> <br>)
                    .replace(/\\n/g, '<br>')   // JSON文字列内のシングルエスケープされた \n を <br> に (例: '\\n' -> <br>)
                    .replace(/\n/g, '<br>')    // 通常の改行文字も <br> に (例: '\n' -> <br>)
                    .replace(/(https?:\\/\\/[^\\s]+)/g, '<a href="$1" target="_blank" class="text-blue-500 hover:underline">$1</a>')
                    .replace(/([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\\.[a-zA-Z0-9_-]+)/g, '<a href="mailto:$1" class="text-blue-500 hover:underline">$1</a>');

                const timeText = document.createElement('span');
                timeText.classList.add('text-xs', 'text-slate-400', 'ml-2');
                timeText.textContent = item.time;

                const iconElement = document.createElement('div');
                iconElement.classList.add('text-2xl', 'pb-1');
                iconElement.textContent = item.icon || '👤';

                if (item.isCurrentUser) {
                    messageWrapper.classList.add('self-end', 'ml-auto');
                    messageBubble.classList.add('bg-blue-500', 'text-white');
                    senderName.classList.add('text-right', 'text-blue-100');
                    messageText.classList.add('text-white');
                    timeText.classList.add('text-blue-200');
                    messageWrapper.appendChild(messageBubble);
                } else {
                    messageWrapper.classList.add('self-start', 'mr-auto');
                    messageBubble.classList.add('bg-white', 'text-slate-700');
                    senderName.classList.add('text-left');
                    timeText.classList.add('text-slate-400');
                    messageWrapper.appendChild(iconElement);
                    messageWrapper.appendChild(messageBubble);
                }
                
                messageBubble.appendChild(senderName);
                messageBubble.appendChild(messageText);
                messageBubble.appendChild(timeText);
                
                chatContainer.appendChild(messageWrapper);
            });
            if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        }
        window.onload = displayMessages;
    </script>""",
        "</body></html>"
    ]
    return "".join(html_parts)

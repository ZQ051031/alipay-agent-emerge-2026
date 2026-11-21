const $ = id => document.getElementById(id);
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = n => '¥' + Number(n).toFixed(2);
async function api(path, body) {
  const response = await fetch('/api/' + path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '输入有误：请检查数量、金额或清单行数。');
  return data;
}
async function render(target, work) {
  $(target).innerHTML = '<div class="card">正在精算…</div>';
  try { $(target).innerHTML = await work(); }
  catch(e) { $(target).innerHTML = '<div class="error" role="alert">' + esc(e.message) + '</div>'; }
}
document.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => {
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b === button));
  document.querySelectorAll('.tab').forEach(s => s.hidden = s.id !== button.dataset.tab);
});
async function shopping() {
  await render('shopping-result', async () => {
    const items = $('shopping-input').value.split('\n').filter(x => x.trim()).map(x => {const [name, quantity = '1'] = x.replace('，', ',').split(',');return {name:name.trim(),quantity:Number(quantity)};});
    const d = await api('compare_grocery_prices', {items});
    if (!items.length) return '<div class="card">先添加几样需要的商品吧。</div>';
    if (d.missing_items.length) return '<div class="card">未找到商品 / 全部价格不可用：' + d.missing_items.map(esc).join('、') + '。请参考商品目录。</div>';
    const split = d.best_split;
    return '<div class="card hero"><div class="muted">最优方案 · 含配送费</div><div class="big">' + (split ? money(split.total) : '暂无可配送方案') + '</div><p>较最贵可下单整篮省 ' + (d.savings === null ? '暂无可比较整篮' : money(d.savings)) + '</p></div><div class="card"><h3>各平台整篮排名</h3>' + (d.ranked_baskets.map((b,i) => '<div class="row"><span>'+(i+1)+'　'+esc(b.platform)+'<div class="muted">配送 '+money(b.delivery_fee)+'</div></span><strong>'+money(b.total)+'</strong></div>').join('') || '<p>无完整且达到起送额的整篮</p>') + '</div><div class="card"><h3>最优拆单建议</h3>' + (split ? split.orders.map(o => '<div class="row"><span>'+esc(o.platform)+'<div class="muted">'+o.items.map(i=>esc(i.name)+' × '+i.quantity).join('、')+'</div></span><b>'+money(o.total)+'</b></div>').join('') : '价格缺失或未达到起送额，不建议凑单。') + '<p>逐商品分配，计入每单配送费与起送限制；不额外加购凑单。</p><details><summary>价格缺失 / 无法组成整篮的平台</summary>'+Object.entries(d.unavailable).filter(([p,n])=>n.length).map(([p,n])=>esc(p)+'：'+n.map(esc).join('、')).join('<br>')+'</details></div>';
  });
}
$('shopping-form').onsubmit = e => {e.preventDefault();shopping();};
async function coupons() {
  await render('coupon-result', async () => {
    const d = await api('best_coupon',{amount:Number($('amount').value),platform:$('platform').value || null,category:$('category').value || null});
    const show = c => c && c.coupons.length ? c.coupons.map(esc).join(' + ')+' · 实付 '+money(c.payable) : '无适用优惠券';
    return '<div class="card hero"><div class="muted">最优组合预计节省</div><div class="big">'+money(d.best_stack.savings)+'</div><p>'+show(d.best_stack)+'</p></div><div class="card"><h3>最佳单券</h3>'+show(d.best_single)+'</div><div class="card"><h3>7天内到期提醒（全部券）</h3>'+ (d.expiry_warnings.map(c=>'<div class="row"><span>'+esc(c.name)+' <small>'+esc(c.id)+'</small></span><span class="warn">'+c.days_left+'天后到期</span></div>').join('') || '暂无即将到期的券') + '<p>过期券与不满足门槛、平台或类别限制的券不会参与推荐。省钱相同时优先使用临期券。</p></div>';
  });
}
$('coupon-form').onsubmit = e => {e.preventDefault();coupons();};
async function init() {
  try {
    const d = await api('data');
    $('catalog').innerHTML = d.groceries.map(i=>esc(i.name)+'：'+esc(i.unit)).join('<br>');
    $('platform').innerHTML += d.platforms.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.name)+'</option>').join('');
    await Promise.all([shopping(),coupons(),
      render('inventory-result',async()=>{
        const d = await api('track_inventory');
        return '<div class="card hero"><h3>待确认补货清单 · '+d.reorder_list.length+' 项</h3><p>'+d.reorder_list.map(i=>esc(i.name)).join('、')+'</p><span class="muted">仅生成清单，不下单。过期物品请先核实处置；药品不作服用建议。</span></div><div class="grid">'+d.items.map(i=>'<div class="card"><span class="badge">'+esc(i.reminder_level)+'</span><h3>'+esc(i.name)+'</h3><div>库存 '+i.stock+' '+esc(i.unit)+'</div><p>预计用尽：'+(i.run_out_date || '无消耗记录，无法预测')+'<br>可用天数：'+(i.days_to_empty ?? '未知')+'<br>距保质期：'+i.expiry_days+' 天</p></div>').join('')+'</div>';
      }),
      render('subscription-result',async()=>{
        const d = await api('audit_subscriptions');
        return '<div class="card hero"><div class="muted">折合每月固定支出</div><div class="big">'+money(d.monthly_total)+'</div><p>季度费用 ÷ 3；年度费用 ÷ 12。不修改任何续费设置。</p></div><div class="card"><table><thead><tr><th>订阅</th><th>折合月费</th><th>风险分</th><th>提醒</th></tr></thead><tbody>'+d.subscriptions.map(s=>'<tr><td>'+esc(s.name)+'</td><td>'+money(s.monthly_cost)+'</td><td>'+s.risk_score+'/100</td><td>'+s.flags.map(esc).join(' · ')+'</td></tr>').join('')+'</tbody></table><p>静默且7天内自动续费 +40；同类重复 +30；每月使用不超过1次 +30。</p></div>';
      })]);
  } catch(e) { $('shopping-result').innerHTML = '<div class="error">'+esc(e.message)+'</div>'; }
}
init();

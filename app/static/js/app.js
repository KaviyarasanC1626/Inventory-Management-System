document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.querySelector('[data-sidebar]');
  document.querySelector('[data-menu-toggle]')?.addEventListener('click', () => sidebar?.classList.toggle('open'));

  document.querySelectorAll('form[data-confirm], form[data-confirm-submit]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      const message = form.dataset.confirm || form.dataset.confirmSubmit;
      if (message && !window.confirm(message)) event.preventDefault();
    });
  });

  document.querySelectorAll('[data-order-form]').forEach((form) => setupOrderForm(form));

  const rangeForm = document.querySelector('[data-report-dates]');
  if (rangeForm) {
    const from = rangeForm.elements.namedItem('from');
    const to = rangeForm.elements.namedItem('to');
    const today = new Date();
    const end = today.toISOString().slice(0, 10);
    const startDate = new Date(today);
    startDate.setDate(startDate.getDate() - 29);
    from.value = startDate.toISOString().slice(0, 10);
    to.value = end;
    const refresh = () => document.querySelectorAll('[data-date-export]').forEach((link) => {
      const url = new URL(link.href);
      if (link.dataset.dateParam === 'as_of') {
        url.searchParams.set('as_of', to.value);
      } else {
        url.searchParams.set('from', from.value);
        url.searchParams.set('to', to.value);
      }
      link.href = url.toString();
    });
    rangeForm.addEventListener('change', refresh);
    document.querySelector('[data-set-range]')?.addEventListener('click', () => {
      to.value = new Date().toISOString().slice(0, 10);
      const date = new Date();
      date.setDate(date.getDate() - 29);
      from.value = date.toISOString().slice(0, 10);
      refresh();
    });
    refresh();
  }
});

function setupOrderForm(form) {
  const kind = form.dataset.kind;
  if (kind === 'sale') {
    form.dataset.idempotencyKey = globalThis.crypto?.randomUUID?.() || `sale-${Date.now()}-${Math.random()}`;
  }
  const root = form.closest('.form-panel');
  const optionData = [...root.querySelectorAll('[data-product-options] span')].map((item) => ({
    id: item.dataset.id,
    sku: item.dataset.sku,
    name: item.dataset.name,
    price: kind === 'purchase' ? item.dataset.cost : item.dataset.price,
  }));
  const rows = form.querySelector('[data-order-lines]');
  const feedback = form.querySelector('.form-feedback');
  const total = form.querySelector('[data-order-total]');

  const refreshTotal = () => {
    const amount = [...rows.querySelectorAll('.order-line')].reduce((sum, row) => {
      const quantity = Number(row.querySelector('[name="quantity"]').value || 0);
      const price = Number(row.querySelector('.line-price').value || 0);
      const discount = kind === 'sale' ? Number(row.querySelector('.line-discount').value || 0) : 0;
      return sum + Math.max(0, quantity * price - discount);
    }, 0);
    total.textContent = `₹${amount.toFixed(2)}`;
  };

  const addRow = () => {
    const row = document.createElement('div');
    row.className = 'order-line';
    const productWrap = document.createElement('div');
    productWrap.className = 'line-product';
    const productLabel = document.createElement('label');
    productLabel.className = 'form-label';
    productLabel.textContent = 'Product';
    const productSelect = document.createElement('select');
    productSelect.className = 'form-select line-product-select';
    productSelect.required = true;
    productSelect.innerHTML = '<option value="">Select product</option>';
    optionData.forEach((product) => {
      const option = document.createElement('option');
      option.value = product.id;
      option.textContent = `${product.sku} · ${product.name}`;
      option.dataset.price = product.price;
      productSelect.append(option);
    });
    productWrap.append(productLabel, productSelect);

    const quantityWrap = document.createElement('div');
    const quantityLabel = document.createElement('label');
    quantityLabel.className = 'form-label';
    quantityLabel.textContent = 'Qty';
    const quantity = document.createElement('input');
    quantity.className = 'form-control';
    quantity.name = 'quantity';
    quantity.type = 'number';
    quantity.min = '1';
    quantity.step = '1';
    quantity.value = '1';
    quantity.required = true;
    quantityWrap.append(quantityLabel, quantity);

    const priceWrap = document.createElement('div');
    priceWrap.className = 'line-price-wrap';
    const priceLabel = document.createElement('label');
    priceLabel.className = 'form-label';
    priceLabel.textContent = kind === 'purchase' ? 'Unit cost' : 'Unit price';
    const price = document.createElement('input');
    price.className = 'form-control line-price';
    price.name = kind === 'purchase' ? 'unit_cost' : 'unit_price';
    price.type = 'number';
    price.min = '0';
    price.step = '0.01';
    price.value = '0.00';
    price.required = true;
    priceWrap.append(priceLabel, price);

    row.append(productWrap, quantityWrap, priceWrap);
    if (kind === 'sale') {
      const discountWrap = document.createElement('div');
      discountWrap.className = 'line-discount-wrap';
      const discountLabel = document.createElement('label');
      discountLabel.className = 'form-label';
      discountLabel.textContent = 'Line discount';
      const discount = document.createElement('input');
      discount.className = 'form-control line-discount';
      discount.name = 'discount_amount';
      discount.type = 'number';
      discount.min = '0';
      discount.step = '0.01';
      discount.value = '0.00';
      discountWrap.append(discountLabel, discount);
      row.append(discountWrap);
    }
    const remove = document.createElement('button');
    remove.className = 'remove-line';
    remove.type = 'button';
    remove.title = 'Remove item';
    remove.setAttribute('aria-label', 'Remove item');
    remove.innerHTML = '<i class="bi bi-trash3"></i>';
    remove.addEventListener('click', () => { row.remove(); refreshTotal(); });
    row.append(remove);
    productSelect.addEventListener('change', () => {
      const selected = productSelect.selectedOptions[0];
      if (selected?.dataset.price) price.value = Number(selected.dataset.price).toFixed(2);
      refreshTotal();
    });
    row.addEventListener('input', refreshTotal);
    rows.append(row);
  };

  form.querySelector('[data-add-line]')?.addEventListener('click', addRow);
  addRow();
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    feedback.textContent = '';
    const items = [...rows.querySelectorAll('.order-line')].map((row) => {
      const item = {
        product_id: Number(row.querySelector('.line-product-select').value),
        quantity: Number(row.querySelector('[name="quantity"]').value),
      };
      item[kind === 'purchase' ? 'unit_cost' : 'unit_price'] = Number(row.querySelector('.line-price').value);
      if (kind === 'sale') item.discount_amount = Number(row.querySelector('.line-discount').value);
      return item;
    });
    if (!items.length || items.some((item) => !item.product_id || !Number.isInteger(item.quantity) || item.quantity < 1)) {
      feedback.textContent = 'Choose a product and positive whole-number quantity for every line.';
      return;
    }
    const body = {
      warehouse_id: Number(form.elements.namedItem('warehouse_id').value),
      items,
      notes: form.elements.namedItem('notes')?.value || '',
    };
    if (kind === 'purchase') body.supplier_id = Number(form.elements.namedItem('supplier_id').value);
    if (kind === 'sale') {
      body.customer_name = form.elements.namedItem('customer_name').value;
      body.discount_amount = Number(form.elements.namedItem('discount_amount').value || 0);
      body.tax_rate = Number(form.elements.namedItem('tax_rate').value || 0);
    }
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Saving…';
    try {
      const headers = { 'Content-Type': 'application/json', 'X-CSRFToken': form.dataset.csrf };
      if (kind === 'sale') headers['Idempotency-Key'] = form.dataset.idempotencyKey;
      const response = await fetch(form.dataset.endpoint, { method: 'POST', headers, body: JSON.stringify(body) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || 'Could not save this order.');
      window.location.assign(form.dataset.successUrl);
    } catch (error) {
      feedback.textContent = error.message;
      submit.disabled = false;
      submit.textContent = kind === 'purchase' ? 'Create pending order' : 'Create pending sale';
    }
  });
}
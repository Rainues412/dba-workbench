/**
 * workbench.js - API 数据层（合并自 dba-workspace 后端）
 *
 * 加载后劫持原页面的 gd()/sd()，把 6 个数据集合的读写切到
 * http://localhost:8686 的 REST API（SQLite 存储）。
 *
 * 设计约束：
 * - 不改动 ops-workbench.html 的任何 UI 样式与渲染逻辑，只替换数据源
 * - 服务器不可用时自动回退 localStorage，页面功能不中断
 * - 密码集合（accounts）始终留在 localStorage，明文密码不上 API
 */
(function () {
  'use strict';

  var API_BASE = window.location.protocol + '//' + window.location.host;
  var P = 'wb_dba_workbench_';
  var LOCAL_ONLY = { accounts: true };   // 永不走 API 的集合
  var KNOWN = { scripts: 1, knowledge: 1, installers: 1, tasks: 1, contacts: 1, accounts: 1 };

  var apiUp = false;          // 服务器是否可用
  var cache = {};             // 集合名 -> 数组（API 模式下的内存缓存）
  var shadow = {};            // 最近一次已知记录快照，用于计算单条变更
  var writeQueue = {};        // 同一集合的写操作串行执行
  var pageState = {};         // 集合名 -> 当前服务端分页状态
  var facets = {};            // 层级导航的服务端聚合计数
  var dashboardStats = {};
  var dashboardRows = {};
  var bootstrapped = false;
  var PAGE_SIZE = 50;

  window.wbPageState = pageState;
  window.wbFacets = facets;
  window.wbDashboardStats = dashboardStats;
  window.wbDashboardRows = dashboardRows;

  // ── 基础工具 ──────────────────────────────────────────────
  function lsGet(k) {
    try { return JSON.parse(localStorage.getItem(P + k) || '[]'); } catch (e) { return []; }
  }
  function lsSet(k, d) { localStorage.setItem(P + k, JSON.stringify(d)); }

  function api(method, path, body, extraHeaders) {
    var headers = { 'Content-Type': 'application/json' };
    Object.keys(extraHeaders || {}).forEach(function (key) { headers[key] = extraHeaders[key]; });
    return fetch(API_BASE + path, {
      method: method,
      headers: headers,
      body: body === undefined ? undefined : JSON.stringify(body)
    }).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (problem) {
          var message = problem.detail || (problem.error && problem.error.message) || ('HTTP ' + r.status);
          var error = new Error(message);
          error.status = r.status;
          throw error;
        });
      }
      return r.json();
    });
  }

  function toastMsg(m) {
    if (typeof window.toast === 'function') window.toast(m);
  }

  function friendlyError(error) {
    if (error.status === 400 || error.status === 422 || error.status === 428) return '数据校验失败：' + error.message;
    if (error.status === 401) return '登录已失效，请重新登录';
    if (error.status === 403) return '没有权限执行此操作';
    if (error.status === 409) return '保存冲突：数据已被其他窗口修改，已刷新';
    if (error.status >= 500) return '服务暂时异常，请稍后重试';
    return '请求失败：' + error.message;
  }

  // ── 字段映射：localStorage 结构 <-> API 结构 ────────────────
  var M = {
    scripts: {
      toApi: function (s) {
        return {
          title: s.name || '', description: s.desc || '', db_type: s.db || '通用',
          tags: (s.tags || []).join(','), content: s.content || '', file_path: s.path || ''
        };
      },
      fromApi: function (r) {
        return {
          id: r.id, name: r.title, type: r.wb_type || '其他', db: r.db_type,
          path: r.file_path || '', desc: r.description || '',
          tags: (r.tags || '').split(',').map(function (t) { return t.trim(); }).filter(Boolean),
          content: r.content || '', createdAt: r.created_at, revision: r.revision
        };
      }
    },
    knowledge: {
      toApi: function (k) {
        return {
          title: k.name || '', summary: k.desc || '', content: k.content || '',
          category: k.category || '运维规范', tags: (k.tags || []).join(','), file_path: k.path || ''
        };
      },
      fromApi: function (r) {
        return {
          id: r.id, name: r.title, category: r.category, db: r.wb_db || '通用',
          path: r.file_path || '', desc: r.summary || '',
          tags: (r.tags || '').split(',').map(function (t) { return t.trim(); }).filter(Boolean),
          content: r.content || '', createdAt: r.created_at, revision: r.revision
        };
      }
    },
    installers: {
      toApi: function (i) {
        return {
          name: i.name || '', kind: i.type || '数据库', path: i.path || '',
          version: i.version || '', size_mb: 0,
          notes: '',
          wb_db: i.db || '通用',
          tags: (i.tags || []).join(',')
        };
      },
      fromApi: function (r) {
        return {
          id: r.id, name: r.name, version: r.version || '', type: r.kind,
          path: r.path || '',
          tags: (r.tags || '').split(',').map(function(t){ return t.trim(); }).filter(Boolean),
          db: r.wb_db || '通用', createdAt: r.created_at, revision: r.revision
        };
      }
    },
    tasks: {
      toApi: function (t) {
        return {
          title: t.title || '', description: t.notes || '',
          priority: t.priority === 'P0' ? '高' : t.priority === 'P1' ? '中' : '低',
          due_date: t.deadline || null,
          status: t.status === 'completed' ? '已完成' : '待处理'
        };
      },
      fromApi: function (r) {
        return {
          id: r.id, title: r.title, deadline: r.due_date || '',
          priority: r.priority === '高' ? 'P0' : r.priority === '中' ? 'P1' : 'P2',
          status: r.status === '已完成' ? 'completed' : 'pending',
          notes: r.description || '', createdAt: r.created_at, revision: r.revision
        };
      }
    },
    contacts: {
      toApi: function (c) {
        return {
          name: c.customer || '', project_name: c.project || '', group_name: c.groupName || '',
          status: c.status || '进行中', notes: c.notes || '',
          wb_person: c.personInCharge || '', wb_contact: c.contact || ''
        };
      },
      fromApi: function (r) {
        return {
          id: r.id, project: r.project_name, customer: r.name, groupName: r.group_name,
          personInCharge: r.wb_person || '', contact: r.wb_contact || '',
          status: r.status, notes: r.notes || '', createdAt: r.created_at, revision: r.revision
        };
      }
    }
  };

  // ── 拉取 / 推送 ────────────────────────────────────────────
  var LIST_PATH = {
    scripts: '/api/scripts/',
    knowledge: '/api/articles/',
    installers: '/api/resources/',
    tasks: '/api/tasks/',
    contacts: '/api/customers/'
  };
  var FACET_PATH = {
    scripts: '/api/scripts/facets',
    knowledge: '/api/articles/facets',
    installers: '/api/resources/facets'
  };

  function copyRows(rows) { return JSON.parse(JSON.stringify(rows || [])); }

  function listUrl(key, page, filters) {
    var params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    Object.keys(filters || {}).forEach(function (name) {
      if (filters[name] !== '' && filters[name] !== null && filters[name] !== undefined) {
        params.set(name, filters[name]);
      }
    });
    return LIST_PATH[key] + '?' + params.toString();
  }

  function pull(key, page, filters) {
    var previous = pageState[key] || {};
    page = page || previous.page || 1;
    filters = filters || previous.filters || {};
    return api('GET', listUrl(key, page, filters)).then(function (d) {
      var rows = (d.items || []).map(M[key].fromApi);
      // 镜像到 localStorage：服务器不可用时回退看到的是真实数据而非示例种子
      try { lsSet(key, rows); } catch (e) {}
      shadow[key] = copyRows(rows);
      pageState[key] = {
        page: d.page, pageSize: d.page_size, pages: d.pages,
        total: d.total, hasNext: d.has_next, hasPrevious: d.has_previous,
        filters: Object.assign({}, filters)
      };
      if (page === 1 && Object.keys(filters).length === 0) dashboardRows[key] = copyRows(rows);
      return rows;
    });
  }

  function pullFacets(key) {
    if (!FACET_PATH[key]) return Promise.resolve();
    return api('GET', FACET_PATH[key]).then(function (data) { facets[key] = data; });
  }

  function pullDashboardStats() {
    return api('GET', '/api/dashboard/stats').then(function (data) {
      Object.keys(dashboardStats).forEach(function (key) { delete dashboardStats[key]; });
      Object.assign(dashboardStats, data);
    });
  }

  function reloadCurrent(key) {
    var state = pageState[key] || { page: 1, filters: {} };
    return Promise.all([pull(key, state.page, state.filters), pullFacets(key), pullDashboardStats()]).then(function (result) {
      cache[key] = result[0];
      refreshUI();
    });
  }

  function delPath(key, id) {
    return { scripts: '/api/scripts/', knowledge: '/api/articles/', installers: '/api/resources/',
             tasks: '/api/tasks/', contacts: '/api/customers/' }[key] + id;
  }

  function payloadFor(key, row, forUpdate) {
    var payload = M[key].toApi(row);
    if (key === 'scripts') payload.wb_type = row.type || '其他';
    if (key === 'knowledge') payload.wb_db = row.db || '通用';
    // 列表响应刻意不含正文；旧页面也不编辑正文，更新时绝不能以空串覆盖它。
    if (forUpdate && (key === 'scripts' || key === 'knowledge')) delete payload.content;
    // 安装包表单未展示以下字段，更新时保持服务端原值。
    if (forUpdate && key === 'installers') {
      delete payload.size_mb;
      delete payload.notes;
    }
    return payload;
  }

  function findMutation(before, after) {
    var oldById = {}, newById = {};
    before.forEach(function (row) { oldById[row.id] = row; });
    after.forEach(function (row) { newById[row.id] = row; });
    var changes = [];
    before.forEach(function (row) {
      if (!newById[row.id]) changes.push({ type: 'delete', old: row });
      else if (JSON.stringify(row) !== JSON.stringify(newById[row.id])) {
        changes.push({ type: 'update', old: row, row: newById[row.id] });
      }
    });
    after.forEach(function (row) {
      if (!oldById[row.id]) changes.push({ type: 'create', row: row });
    });
    return changes;
  }

  function replaceCachedRow(key, oldId, apiRow) {
    var mapped = M[key].fromApi(apiRow);
    var index = (cache[key] || []).findIndex(function (row) { return row.id === oldId; });
    if (index >= 0) cache[key][index] = mapped;
    shadow[key] = copyRows(cache[key]);
    try { lsSet(key, cache[key]); } catch (e) {}
  }

  function persistMutation(key, mutation) {
    if (mutation.type === 'create') {
      return api('POST', delPath(key, ''), payloadFor(key, mutation.row, false)).then(function (created) {
        replaceCachedRow(key, mutation.row.id, created);
      });
    }
    var headers = { 'If-Match': String(mutation.old.revision) };
    if (mutation.type === 'delete') {
      return api('DELETE', delPath(key, mutation.old.id), undefined, headers).then(function () {
        shadow[key] = copyRows(cache[key]);
        try { lsSet(key, cache[key]); } catch (e) {}
      });
    }
    var merged = Object.assign({}, mutation.old, mutation.row);
    return api('PUT', delPath(key, mutation.row.id), payloadFor(key, merged, true), headers)
      .then(function (updated) { replaceCachedRow(key, mutation.row.id, updated); });
  }

  function queueMutation(key, mutation) {
    writeQueue[key] = (writeQueue[key] || Promise.resolve()).then(function () {
      return persistMutation(key, mutation);
    }).then(function () {
      return reloadCurrent(key);
    }).catch(function (error) {
      toastMsg(friendlyError(error));
      return reloadCurrent(key);
    });
  }

  // ── 劫持 gd / sd ───────────────────────────────────────────
  function hijack() {
    window.gd = function (k) {
      if (LOCAL_ONLY[k] || !apiUp) return lsGet(k);
      if (!cache[k]) cache[k] = [];
      return cache[k];
    };
    window.sd = function (k, d) {
      if (LOCAL_ONLY[k] || !apiUp) { lsSet(k, d); return; }
      var changes = findMutation(shadow[k] || [], d || []);
      if (changes.length !== 1) {
        toastMsg('拒绝批量覆盖：每次只能修改一条记录');
        pull(k).then(function (fresh) { cache[k] = fresh; refreshUI(); });
        return;
      }
      cache[k] = d;
      shadow[k] = copyRows(d);
      queueMutation(k, changes[0]);
    };
  }

  // ── 启动 ───────────────────────────────────────────────────
  function bootstrap() {
    return pullDashboardStats().then(function () {
      apiUp = true;
      var lists = Object.keys(LIST_PATH).map(function (k) {
        return pull(k, 1, {}).then(function (rows) { cache[k] = rows; });
      });
      var counts = Object.keys(FACET_PATH).map(pullFacets);
      return Promise.all(lists.concat(counts));
    }).then(function () {
      hijack();
      bootstrapped = true;
      // 服务器有数据而本地 localStorage 还是种子数据时，以服务器为准
      refreshUI();
      renderAllPagers();
      showApiBadge(true);
    }).catch(function () {
      apiUp = false;
      showApiBadge(false);
    });
  }

  function refreshUI() {
    ['renderDashboard', 'renderScripts', 'renderKnowledge', 'renderInstallers',
     'renderTasks', 'renderContacts'].forEach(function (fn) {
      if (typeof window[fn] === 'function') { try { window[fn](); } catch (e) {} }
    });
    renderAllPagers();
  }

  function renderPager(key) {
    var bodyId = {
      scripts: 'scriptsTableBody', knowledge: 'knowledgeTableBody',
      installers: 'installersTableBody', tasks: 'tasksTableBody', contacts: 'contactsTableBody'
    }[key];
    var body = document.getElementById(bodyId);
    var state = pageState[key];
    if (!body || !state) return;
    var table = body.closest('table');
    if (!table) return;
    var pager = document.getElementById('wbPager-' + key);
    if (!pager) {
      pager = document.createElement('div');
      pager.id = 'wbPager-' + key;
      pager.style.cssText = 'display:flex;justify-content:flex-end;align-items:center;gap:10px;padding:12px 0;color:#64748b;font-size:13px';
      table.insertAdjacentElement('afterend', pager);
    }
    var pages = state.pages || 0;
    pager.replaceChildren();
    var label = document.createElement('span');
    label.textContent = '共 ' + state.total + ' 条 · 第 ' + (pages ? state.page : 0) + ' / ' + pages + ' 页';
    var prev = document.createElement('button');
    prev.className = 'btn-secondary';
    prev.textContent = '上一页';
    prev.disabled = !state.hasPrevious;
    prev.onclick = function () { window.wbChangePage(key, state.page - 1); };
    var next = document.createElement('button');
    next.className = 'btn-secondary';
    next.textContent = '下一页';
    next.disabled = !state.hasNext;
    next.onclick = function () { window.wbChangePage(key, state.page + 1); };
    pager.append(label, prev, next);
  }

  function renderAllPagers() { Object.keys(LIST_PATH).forEach(renderPager); }

  window.wbChangePage = function (key, page) {
    var state = pageState[key];
    if (!state || page < 1 || (state.pages && page > state.pages)) return;
    pull(key, page, state.filters).then(function (rows) {
      cache[key] = rows;
      refreshUI();
    }).catch(function (error) { toastMsg('翻页失败：' + error.message); });
  };

  function installServerPagination() {
    var originalSwitchView = window.switchView;
    if (typeof originalSwitchView === 'function') {
      window.switchView = function (view) {
        originalSwitchView(view);
        var request;
        if (view === 'scripts' && window._selectedScriptDB && window._selectedScriptType) {
          request = pull('scripts', 1, { db_type: window._selectedScriptDB, wb_type: window._selectedScriptType });
        } else if (view === 'knowledge' && window._selectedKbDB && window._selectedKbType) {
          request = pull('knowledge', 1, { wb_db: window._selectedKbDB, category: window._selectedKbType });
        } else if (view === 'installers' && window._selectedInstDB) {
          request = pull('installers', 1, { wb_db: window._selectedInstDB });
        }
        if (request) request.then(function (rows) {
          cache[view === 'knowledge' ? 'knowledge' : view] = rows;
          refreshUI();
        });
      };
    }
    var originalScriptType = window.scriptSelectType;
    if (typeof originalScriptType === 'function') {
      window.scriptSelectType = function (type) {
        originalScriptType(type);
        pull('scripts', 1, { db_type: window._selectedScriptDB, wb_type: type }).then(function (rows) {
          cache.scripts = rows; refreshUI();
        });
      };
    }
    var originalKbType = window.kbSelectType;
    if (typeof originalKbType === 'function') {
      window.kbSelectType = function (type) {
        originalKbType(type);
        pull('knowledge', 1, { wb_db: window._selectedKbDB, category: type }).then(function (rows) {
          cache.knowledge = rows; refreshUI();
        });
      };
    }
    var originalInstDb = window.instSelectDB;
    if (typeof originalInstDb === 'function') {
      window.instSelectDB = function (name) {
        originalInstDb(name);
        pull('installers', 1, { wb_db: name }).then(function (rows) {
          cache.installers = rows; refreshUI();
        });
      };
    }
    window.wbTaskFiltersChanged = function () {
      var priority = document.getElementById('filterTaskPriority').value;
      var status = document.getElementById('filterTaskStatus').value;
      var priorities = { P0: '高', P1: '中', P2: '低' };
      var statuses = { pending: '待处理', completed: '已完成' };
      pull('tasks', 1, {
        priority: priorities[priority] || '', status: statuses[status] || ''
      }).then(function (rows) { cache.tasks = rows; refreshUI(); })
        .catch(function (error) { toastMsg('筛选失败：' + error.message); });
    };
  }

  var searchTimer;
  window.wbSearch = function (query) {
    clearTimeout(searchTimer);
    if (!query.trim()) return;
    searchTimer = setTimeout(function () {
      api('GET', '/api/search/?q=' + encodeURIComponent(query) + '&limit=100').then(function (result) {
        var count = Object.keys(result).reduce(function (sum, key) {
          return sum + (Array.isArray(result[key]) ? result[key].length : 0);
        }, 0);
        toastMsg(count ? '找到 ' + count + ' 个相关结果' : '没有找到相关结果');
      }).catch(function (error) { toastMsg('搜索失败：' + error.message); });
    }, 250);
  };

  function installDetailLoading() {
    [
      ['editScript', 'scripts'], ['editKnowledge', 'knowledge'],
      ['editInstaller', 'installers'], ['editTask', 'tasks'], ['editContact', 'contacts']
    ].forEach(function (pair) {
      var original = window[pair[0]], key = pair[1];
      if (typeof original !== 'function') return;
      window[pair[0]] = function (id) {
        api('GET', delPath(key, id)).then(function (record) {
          replaceCachedRow(key, id, record);
          original(id);
        }).catch(function (error) { toastMsg('加载详情失败：' + error.message); });
      };
    });
  }

  function showApiBadge(up) {
    var el = document.getElementById('apiBadge');
    if (!el) {
      el = document.createElement('span');
      el.id = 'apiBadge';
      el.style.cssText = 'font-size:11px;padding:2px 8px;border-radius:4px;margin-left:8px;vertical-align:middle';
      var sub = document.querySelector('.sidebar-header .sidebar-sub');
      if (sub) sub.parentNode.insertBefore(el, sub.nextSibling);
    }
    if (up) { el.textContent = '已连接服务器'; el.style.background = '#dcfce7'; el.style.color = '#166534'; }
    else { el.textContent = '本地模式'; el.style.background = '#fef3c7'; el.style.color = '#d97706'; }
  }

  // ── 扩展能力：打开本地文件 / 扫描入库 ──────────────────────
  // 在「复制路径」旁边注入「打开」按钮：改写三个 render 函数的输出
  function enhanceOpenButtons() {
    ['scripts', 'knowledge', 'installers'].forEach(function (key) {
      var renderName = 'render' + key.charAt(0).toUpperCase() + key.slice(1);
      var orig = window[renderName];
      if (typeof orig !== 'function') return;
      window[renderName] = function () {
        orig();
        var bodyId = { scripts: 'scriptsTableBody', knowledge: 'knowledgeTableBody', installers: 'installersTableBody' }[key];
        var tbody = document.getElementById(bodyId);
        if (!tbody) return;
        // For hierarchical views, filter to only visible rows
        var rows;
        if (key === 'knowledge' && typeof _selectedKbDB !== 'undefined' && _selectedKbDB && _selectedKbType) {
          rows = window.gd(key).filter(function(k){ return k.db === _selectedKbDB && k.category === _selectedKbType; });
        } else if (key === 'installers' && typeof _selectedInstDB !== 'undefined' && _selectedInstDB) {
          rows = window.gd(key).filter(function(i){ return i.db === _selectedInstDB; });
        } else {
          rows = window.gd(key);
        }
        var trs = tbody.querySelectorAll('tr');
        for (var i = 0; i < trs.length && i < rows.length; i++) {
          (function (tr, row) {
            if (!row.path) return;
            var btn = document.createElement('button');
            btn.className = 'action-btn btn-copy';
            btn.textContent = '打开';
            btn.title = row.path;
            btn.onclick = function () { openLocal(row.path, 'open'); };
            var btn2 = document.createElement('button');
            btn2.className = 'action-btn btn-copy';
            btn2.textContent = '定位';
            btn2.title = '打开所在文件夹';
            btn2.onclick = function () { openLocal(row.path, 'folder'); };
            var cell = tr.querySelector('td:last-child');
            if (cell) { cell.insertBefore(btn2, cell.firstChild); cell.insertBefore(btn, cell.firstChild); }
          })(trs[i], rows[i]);
        }
      };
    });
  }

  function openLocal(path, mode) {
    if (!apiUp) { toastMsg('打开功能需要启动本地服务器（server/main.py）'); return; }
    api('POST', '/api/launcher/path', { path: path, mode: mode || 'open' })
      .then(function () { toastMsg('已打开: ' + path); })
      .catch(function (e) { toastMsg('打开失败: ' + (e.message || e)); });
  }
  window.openLocal = openLocal;

  // 扫描入库：设置页注入入口
  function enhanceSettings() {
    var orig = window.showSettings;
    if (typeof orig !== 'function') return;
    window.showSettings = function () {
      orig();
      var ct = document.getElementById('modalContent');
      if (!ct) return;
      var grp = document.createElement('div');
      grp.className = 'form-group';
      grp.innerHTML = '<label class="form-label">扫描入库（索引本地目录，不移动文件）</label>' +
        '<div style="display:flex;gap:12px;flex-wrap:wrap">' +
        '<button class="btn-secondary" onclick="wbScan()">扫描并入库</button>' +
        '<button class="btn-secondary" onclick="wbListScanDirs()">扫描目录</button>' +
        '</div><div id="wbScanResult" style="margin-top:8px;font-size:13px;color:#64748b"></div>';
      var danger = ct.querySelector('.form-group:last-of-type');
      if (danger) ct.insertBefore(grp, danger); else ct.appendChild(grp);
    };
  }

  window.wbListScanDirs = function () {
    if (!apiUp) { toastMsg('需要启动本地服务器'); return; }
    api('GET', '/api/scan/dirs').then(function (dirs) {
      var el = document.getElementById('wbScanResult');
      el.replaceChildren();
      if (dirs.length) {
        dirs.forEach(function (d) {
          var row = document.createElement('div');
          row.textContent = '• ' + d.path;
          el.appendChild(row);
        });
      } else {
        var empty = document.createElement('div');
        empty.textContent = '尚未配置扫描目录，请先用 wbAddScanDir("路径") 添加（浏览器控制台）';
        el.appendChild(empty);
      }
    });
  };
  window.wbAddScanDir = function (p) {
    api('POST', '/api/scan/dirs', { path: p }).then(function () { toastMsg('目录已添加'); window.wbListScanDirs(); })
      .catch(function (e) { toastMsg('添加失败: ' + (e.detail || e.message)); });
  };
  window.wbScan = function () {
    if (!apiUp) { toastMsg('需要启动本地服务器'); return; }
    var el = document.getElementById('wbScanResult');
    el.textContent = '扫描中...';
    api('POST', '/api/scan/run', {}).then(function (d) {
      var items = d.items || [];
      if (!items.length) { el.textContent = '没有发现未登记的文件'; return; }
      el.textContent = '发现 ' + items.length + ' 个新文件，入库中...';
      return api('POST', '/api/scan/commit', { items: items }).then(function (c) {
        el.textContent = '入库完成: 资源 ' + (c.imported.resource || 0) + ' / 文档 ' +
          (c.imported.article || 0) + ' / 脚本 ' + (c.imported.script || 0);
        return Promise.all(Object.keys(LIST_PATH).map(function (k) {
          return reloadCurrent(k);
        })).then(refreshUI);
      });
    }).catch(function (e) { el.textContent = '扫描失败: ' + (e.message || e); });
  };

  // ── 入口 ───────────────────────────────────────────────────
  function start() {
    bootstrap().then(function () {
      enhanceOpenButtons();
      enhanceSettings();
      installServerPagination();
      installDetailLoading();
      renderAllPagers();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();

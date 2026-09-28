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

  var API_BASE = 'http://localhost:8686';
  var P = 'wb_dba_workbench_';
  var LOCAL_ONLY = { accounts: true };   // 永不走 API 的集合
  var KNOWN = { scripts: 1, knowledge: 1, installers: 1, tasks: 1, contacts: 1, accounts: 1 };

  var apiUp = false;          // 服务器是否可用
  var cache = {};             // 集合名 -> 数组（API 模式下的内存缓存）
  var pending = {};           // 集合名 -> 待落盘的防抖定时器
  var bootstrapped = false;

  // ── 基础工具 ──────────────────────────────────────────────
  function lsGet(k) {
    try { return JSON.parse(localStorage.getItem(P + k) || '[]'); } catch (e) { return []; }
  }
  function lsSet(k, d) { localStorage.setItem(P + k, JSON.stringify(d)); }

  function api(method, path, body) {
    return fetch(API_BASE + path, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body)
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function toastMsg(m) {
    if (typeof window.toast === 'function') window.toast(m);
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
          content: r.content || '', createdAt: r.created_at
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
          content: r.content || '', createdAt: r.created_at
        };
      }
    },
    installers: {
      toApi: function (i) {
        return {
          name: i.name || '', kind: i.type || '数据库', path: i.path || '',
          version: i.version || '', size_mb: parseFloat(i.size) || 0, notes: i.size && isNaN(parseFloat(i.size)) ? i.size : ''
        };
      },
      fromApi: function (r) {
        return {
          id: r.id, name: r.name, version: r.version || '', type: r.kind,
          path: r.path || '', size: r.notes || (r.size_mb ? r.size_mb + ' MB' : ''),
          createdAt: r.created_at
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
          notes: r.description || '', createdAt: r.created_at
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
          status: r.status, notes: r.notes || '', createdAt: r.created_at
        };
      }
    }
  };

  // ── 拉取 / 推送 ────────────────────────────────────────────
  var LIST_PATH = {
    scripts: '/api/scripts/?page_size=500',
    knowledge: '/api/articles/?page_size=1000',
    installers: '/api/resources/?page_size=500',
    tasks: '/api/tasks/?page_size=500',
    contacts: '/api/customers/'
  };

  function pull(key) {
    return api('GET', LIST_PATH[key]).then(function (d) {
      var rows = (d.items || []).map(M[key].fromApi);
      // 镜像到 localStorage：服务器不可用时回退看到的是真实数据而非示例种子
      try { lsSet(key, rows); } catch (e) {}
      return rows;
    });
  }

  function pushAll(key) {
    var rows = cache[key] || [];
    // 全量替换：先删服务端多余的，再逐条 upsert
    return api('GET', LIST_PATH[key]).then(function (d) {
      var serverIds = {};
      (d.items || []).forEach(function (r) { serverIds[r.id] = true; });
      var localIds = {};
      rows.forEach(function (r) { if (r.id) localIds[r.id] = true; });
      var dels = Object.keys(serverIds).filter(function (id) { return !localIds[id]; })
        .map(function (id) { return api('DELETE', delPath(key, id)).catch(function () {}); });
      return Promise.all(dels).then(function () {
        return rows.reduce(function (chain, row) {
          return chain.then(function () { return upsert(key, row); });
        }, Promise.resolve());
      });
    }).then(function () {
      // 刷新缓存 id（新建条目拿到服务端 id）
      return pull(key).then(function (fresh) { cache[key] = fresh; });
    });
  }

  function delPath(key, id) {
    return { scripts: '/api/scripts/', knowledge: '/api/articles/', installers: '/api/resources/',
             tasks: '/api/tasks/', contacts: '/api/customers/' }[key] + id;
  }

  function upsert(key, row) {
    var payload = M[key].toApi(row);
    if (key === 'scripts') payload.wb_type = row.type || '其他';
    if (key === 'knowledge') payload.wb_db = row.db || '通用';
    if (row.id && typeof row.id === 'number' && row.id < 1e12) {
      return api('PUT', delPath(key, row.id), payload).catch(function () {
        return api('POST', delPath(key, ''), payload);
      });
    }
    return api('POST', delPath(key, ''), payload);
  }

  function schedulePush(key) {
    clearTimeout(pending[key]);
    pending[key] = setTimeout(function () {
      pushAll(key).then(refreshUI).catch(function (e) {
        console.warn('[workbench] 同步失败，数据保留在本地缓存:', key, e);
      });
    }, 400);
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
      cache[k] = d;
      schedulePush(k);
    };
  }

  // ── 启动 ───────────────────────────────────────────────────
  function bootstrap() {
    return api('GET', '/api/dashboard/stats').then(function () {
      apiUp = true;
      return Promise.all(Object.keys(LIST_PATH).map(function (k) {
        return pull(k).then(function (rows) { cache[k] = rows; });
      }));
    }).then(function () {
      hijack();
      bootstrapped = true;
      // 服务器有数据而本地 localStorage 还是种子数据时，以服务器为准
      refreshUI();
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
      var orig = window['render' + key.charAt(0).toUpperCase() + key.slice(1)];
      if (typeof orig !== 'function') return;
      window['render' + key.charAt(0).toUpperCase() + key.slice(1)] = function () {
        orig();
        var bodyId = { scripts: 'scriptsTableBody', knowledge: 'knowledgeTableBody', installers: 'installersTableBody' }[key];
        var tbody = document.getElementById(bodyId);
        if (!tbody) return;
        var rows = window.gd(key);
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
      el.innerHTML = dirs.length
        ? dirs.map(function (d) { return '<div>• ' + d.path + '</div>'; }).join('')
        : '<div>尚未配置扫描目录，请先用 wbAddScanDir("路径") 添加（浏览器控制台）</div>';
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
          return pull(k).then(function (rows) { cache[k] = rows; });
        })).then(refreshUI);
      });
    }).catch(function (e) { el.textContent = '扫描失败: ' + (e.message || e); });
  };

  // ── 入口 ───────────────────────────────────────────────────
  function start() {
    bootstrap().then(function () {
      enhanceOpenButtons();
      enhanceSettings();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();

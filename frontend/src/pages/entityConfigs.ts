import { CrudConfig } from "../components/CrudPage";
import { BookOpenText, Building2, ListTodo, PackageOpen, ScrollText } from "lucide-react";

export const scriptsConfig: CrudConfig = {
  key: "scripts", title: "脚本库", description: "按数据库与用途管理可复用脚本。", path: "/api/scripts/", icon: ScrollText,
  classification: { databaseField: "db_type", categoryField: "wb_type", categoryLabel: "脚本类型" },
  fileLinks: { pathField: "file_path", openMode: "edit", openLabel: "打开脚本" },
  columns: [{ name: "title", label: "名称" }, { name: "db_type", label: "数据库" }, { name: "wb_type", label: "类型" }, { name: "updated_at", label: "更新时间" }],
  fields: [
    { name: "title", label: "名称", required: true }, { name: "db_type", label: "数据库", defaultValue: "通用", options: ["Oracle", "MySQL", "PostgreSQL", "SQL Server", "Linux", "Redis", "通用", "其他"] },
    { name: "wb_type", label: "类型", type: "select", defaultValue: "其他", options: ["巡检", "备份", "部署", "监控", "性能", "其他"] }, { name: "tags", label: "标签" },
    { name: "file_path", label: "文件路径" }, { name: "description", label: "说明", type: "textarea" },
    { name: "content", label: "脚本正文", type: "textarea" },
  ],
};

export const articlesConfig: CrudConfig = {
  key: "articles", title: "知识库", description: "按数据库与文档分类查找和维护知识。", path: "/api/articles/", icon: BookOpenText,
  classification: { databaseField: "wb_db", categoryField: "category", categoryLabel: "文档分类" },
  fileLinks: { pathField: "file_path", openMode: "open", openLabel: "打开文档" },
  columns: [{ name: "title", label: "标题" }, { name: "wb_db", label: "数据库" }, { name: "category", label: "分类" }, { name: "updated_at", label: "更新时间" }],
  fields: [
    { name: "title", label: "标题", required: true }, { name: "wb_db", label: "数据库", defaultValue: "通用", options: ["Oracle", "MySQL", "PostgreSQL", "SQL Server", "Linux", "Redis", "通用", "其他"] },
    { name: "category", label: "分类", type: "select", defaultValue: "学习记录", options: ["技术文档", "排障手册", "安装部署", "备份恢复", "架构设计", "性能调优", "安全加固", "迁移方案", "巡检规范", "学习笔记", "学习记录"] }, { name: "tags", label: "标签" },
    { name: "file_path", label: "文件路径" }, { name: "summary", label: "摘要", type: "textarea" },
    { name: "content", label: "正文", type: "textarea" },
  ],
};

export const resourcesConfig: CrudConfig = {
  key: "resources", title: "资源与快捷入口", description: "安装包、工具、本地路径和网址统一索引。", path: "/api/resources/", icon: PackageOpen,
  classification: { databaseField: "wb_db" },
  fileLinks: { pathField: "path", urlField: "url", openMode: "open", openLabel: "打开资源" },
  columns: [{ name: "name", label: "名称" }, { name: "kind", label: "类型" }, { name: "wb_db", label: "数据库" }, { name: "version", label: "版本" }],
  fields: [
    { name: "name", label: "名称", required: true }, { name: "kind", label: "类型", type: "select", defaultValue: "安装包", options: ["安装包", "软件工具", "驱动/固件", "文档资料", "脚本工具", "网址", "其他"] },
    { name: "path", label: "本地路径" }, { name: "url", label: "网址", type: "url" }, { name: "version", label: "版本" },
    { name: "size_mb", label: "大小（MB）", type: "number" }, { name: "category", label: "分类" }, { name: "wb_db", label: "数据库", defaultValue: "通用", options: ["Oracle", "MySQL", "PostgreSQL", "SQL Server", "Linux", "Redis", "通用", "其他"] },
    { name: "tags", label: "标签" }, { name: "notes", label: "备注", type: "textarea" },
  ],
};

export const tasksConfig: CrudConfig = {
  key: "tasks", title: "任务", description: "跟踪优先级、截止日期与完成状态。", path: "/api/tasks/", icon: ListTodo,
  columns: [{ name: "title", label: "任务" }, { name: "priority", label: "优先级" }, { name: "status", label: "状态" }, { name: "due_date", label: "截止日期" }, { name: "created_at", label: "创建时间" }],
  fields: [
    { name: "title", label: "任务", required: true }, { name: "priority", label: "优先级", type: "select", defaultValue: "中", options: ["高", "中", "低"] },
    { name: "status", label: "状态", type: "select", defaultValue: "待处理", options: ["待处理", "进行中", "已完成"] },
    { name: "due_date", label: "截止日期", type: "date" }, { name: "description", label: "说明", type: "textarea" },
  ],
};

export const customersConfig: CrudConfig = {
  key: "customers", title: "客户项目", description: "集中查看客户项目、负责人及联系信息。", path: "/api/customers/", icon: Building2,
  columns: [{ name: "name", label: "客户" }, { name: "project_name", label: "项目" }, { name: "wb_person", label: "负责人" }, { name: "status", label: "状态" }],
  fields: [
    { name: "name", label: "客户", required: true }, { name: "project_name", label: "项目" }, { name: "group_name", label: "分组" },
    { name: "status", label: "状态", type: "select", defaultValue: "活跃", options: ["活跃", "进行中", "已暂停", "已结束"] },
    { name: "wb_person", label: "负责人" }, { name: "wb_contact", label: "联系方式" }, { name: "notes", label: "备注", type: "textarea" },
  ],
};

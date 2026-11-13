import { useEffect, useRef, useState, type ComponentProps } from "react";
import DatePicker, { CalendarContainer } from "react-datepicker";
import { format, isValid, parse } from "date-fns";
import { zhCN } from "date-fns/locale/zh-CN";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import "react-datepicker/dist/react-datepicker.css";

function parseDate(value: string) {
  const date = parse(value, "yyyy-MM-dd", new Date());
  return isValid(date) && format(date, "yyyy-MM-dd") === value ? date : null;
}

function DateCalendar({ className, children }: ComponentProps<typeof CalendarContainer>) {
  return <div className={className} role="dialog" aria-label="选择日期">{children}</div>;
}

export function DateField({ name, label, initialValue, required }: { name: string; label: string; initialValue: string; required?: boolean }) {
  const [selected, setSelected] = useState(() => parseDate(initialValue));
  const [inputValue, setInputValue] = useState(selected ? initialValue : "");
  const [centered, setCentered] = useState(false);
  const picker = useRef<DatePicker>(null);
  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 560px), (max-height: 800px)");
    if (!media) return;
    const update = () => setCentered(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  function selectDate(date: Date | null) {
    setSelected(date);
    setInputValue(date ? format(date, "yyyy-MM-dd") : "");
    if (picker.current?.input instanceof HTMLInputElement) picker.current.input.setCustomValidity("");
  }

  return <div className="workbench-date-field"><DatePicker
    ref={picker}
    name={name}
    ariaLabel={label}
    selected={selected}
    value={inputValue}
    onChange={selectDate}
    onSelect={selectDate}
    onChangeRaw={(event) => {
      const input = event?.target;
      if (!(input instanceof HTMLInputElement)) return;
      setInputValue(input.value);
      input.setCustomValidity(input.value && !parseDate(input.value) ? "请输入有效日期，格式为 YYYY-MM-DD" : "");
    }}
    onKeyDown={(event) => {
      if (event.key === "ArrowDown" && picker.current && !picker.current.isCalendarOpen()) {
        event.preventDefault();
        picker.current.setOpen(true);
      }
    }}
    dateFormat="yyyy-MM-dd"
    locale={zhCN}
    strictParsing
    required={required}
    autoComplete="off"
    placeholderText={required ? "选择日期" : "选择日期（可留空）"}
    calendarClassName="workbench-calendar"
    popperClassName="workbench-date-popper"
    calendarContainer={DateCalendar}
    portalId="workbench-date-portal"
    withPortal={centered}
    popperProps={{ strategy: "fixed" }}
    popperPlacement="bottom"
    showPopperArrow={false}
    preventOpenOnFocus
    showIcon
    icon={<CalendarDays size={17} aria-hidden="true" />}
    toggleCalendarOnIconClick
    isClearable={!required}
    clearButtonTitle="清除日期"
    ariaLabelClose="清除日期"
    todayButton={<button type="button">今天</button>}
    chooseDayAriaLabelPrefix="选择"
    disabledDayAriaLabelPrefix="不可选择"
    renderCustomHeader={({ date, changeYear, changeMonth, decreaseMonth, increaseMonth, prevMonthButtonDisabled, nextMonthButtonDisabled }) => {
      // Match the library's year-dropdown range while retaining out-of-range dates.
      const firstYear = Math.min(1900, date.getFullYear());
      const lastYear = Math.max(2100, date.getFullYear());
      return <div className="date-calendar-heading">
        <button type="button" className="icon-button" aria-label="上个月" title="上个月" disabled={prevMonthButtonDisabled} onClick={decreaseMonth}><ChevronLeft size={17} /></button>
        <div className="date-calendar-selects">
          <select aria-label="年份" value={date.getFullYear()} onChange={(event) => changeYear(Number(event.target.value))}>
            {Array.from({ length: lastYear - firstYear + 1 }, (_, index) => firstYear + index)
              .map((year) => <option key={year} value={year}>{year}年</option>)}
          </select>
          <select aria-label="月份" value={date.getMonth()} onChange={(event) => changeMonth(Number(event.target.value))}>
            {Array.from({ length: 12 }, (_, month) => <option key={month} value={month}>{month + 1}月</option>)}
          </select>
        </div>
        <button type="button" className="icon-button" aria-label="下个月" title="下个月" disabled={nextMonthButtonDisabled} onClick={increaseMonth}><ChevronRight size={17} /></button>
      </div>;
    }}
  /></div>;
}

import { useState } from "react";
import { useCombobox } from "downshift";
import { Check, ChevronDown } from "lucide-react";

export function VaultCategoryInput({ categories, initialValue }: { categories: string[]; initialValue: string }) {
  const [inputValue, setInputValue] = useState(initialValue);
  const [filterInput, setFilterInput] = useState(false);
  const query = inputValue.trim().toLocaleLowerCase();
  const options = filterInput ? categories.filter((category) => category.toLocaleLowerCase().includes(query)) : categories;
  const { isOpen, highlightedIndex, getLabelProps, getInputProps, getToggleButtonProps, getMenuProps, getItemProps } = useCombobox({
    items: options,
    inputValue,
    initialSelectedItem: categories.includes(initialValue) ? initialValue : null,
    onInputValueChange: ({ inputValue }) => setInputValue(inputValue),
  });

  return <div className="vault-category-field">
    <label {...getLabelProps()}>分类</label>
    <div className="vault-category-control">
      <input {...getInputProps({ name: "category", placeholder: "输入或选择已有分类", autoComplete: "off", onChange: () => setFilterInput(true) })} />
      <button {...getToggleButtonProps({ type: "button", "aria-label": "选择已有分类", title: "选择已有分类", onClick: () => setFilterInput(false) })} className="icon-button"><ChevronDown size={17} aria-hidden="true" /></button>
    </div>
    <ul {...getMenuProps()} className="vault-category-menu" hidden={!isOpen}>
      {isOpen && (options.length ? options.map((category, index) => <li {...getItemProps({ item: category, index })} key={category} title={category} className={highlightedIndex === index ? "is-highlighted" : undefined}><span>{category}</span>{inputValue === category && <Check size={15} aria-hidden="true" />}</li>) : <li className="vault-category-empty">{categories.length ? "无匹配分类，可直接输入新分类" : "暂无分类，可直接输入新分类"}</li>)}
    </ul>
  </div>;
}

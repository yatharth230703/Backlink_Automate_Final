import asyncio
from typing import List, Dict, Any, Optional
from playwright.async_api import Page, Locator
import platform

class EnhancedInputHandler:
    """Enhanced input handler with improved dropdown support"""
    
    def __init__(self, page: Page):
        self.page = page
        self.select_all = "Meta+A" if platform.system() == "Darwin" else "Control+A"
    
    async def get_element_info(self, x: float, y: float) -> Dict[str, Any]:
        """Get detailed information about element at coordinates"""
        try:
            element_info = await self.page.evaluate(f"""
                () => {{
                    const element = document.elementFromPoint({x}, {y});
                    if (!element) return null;
                    
                    // Check if we clicked on a label that might be associated with a checkbox/radio
                    let targetElement = element;
                    let wasLabelClicked = false;
                    
                    if (element.tagName.toLowerCase() === 'label') {{
                        wasLabelClicked = true;
                        console.log('Clicked on label:', element.textContent.substring(0, 50));
                        
                        // Try to find the associated input element
                        const forAttr = element.getAttribute('for');
                        if (forAttr) {{
                            const associatedInput = document.getElementById(forAttr);
                            if (associatedInput && (associatedInput.type === 'checkbox' || associatedInput.type === 'radio')) {{
                                targetElement = associatedInput;
                                console.log('Found associated input via for attribute:', associatedInput.type);
                            }}
                        }} else {{
                            // Look for input within the label
                            const inputInLabel = element.querySelector('input[type="checkbox"], input[type="radio"]');
                            if (inputInLabel) {{
                                targetElement = inputInLabel;
                                console.log('Found input within label:', inputInLabel.type);
                            }}
                        }}
                    }}
                    
                    // If still not a checkbox/radio, look for nearby ones (enhanced search)
                    if (targetElement.tagName.toLowerCase() !== 'input' || 
                        (targetElement.type !== 'checkbox' && targetElement.type !== 'radio')) {{
                        
                        console.log('Looking for nearby checkboxes/radios...');
                        // Look for nearby checkboxes/radios within 100px
                        const allInputs = document.querySelectorAll('input[type="checkbox"], input[type="radio"]');
                        let closestInput = null;
                        let closestDistance = Infinity;
                        
                        for (let input of allInputs) {{
                            const rect = input.getBoundingClientRect();
                            const inputCenterX = rect.left + rect.width / 2;
                            const inputCenterY = rect.top + rect.height / 2;
                            
                            const distance = Math.sqrt(
                                Math.pow({x} - inputCenterX, 2) + 
                                Math.pow({y} - inputCenterY, 2)
                            );
                            
                            console.log(`Found ${{input.type}} at distance ${{distance.toFixed(1)}}px`);
                            
                            if (distance < closestDistance && distance <= 100) {{
                                closestDistance = distance;
                                closestInput = input;
                            }}
                        }}
                        
                        if (closestInput) {{
                            targetElement = closestInput;
                            console.log(`Using closest ${{closestInput.type}} at distance ${{closestDistance.toFixed(1)}}px`);
                        }}
                    }}
                    
                    // Also check if the clicked element contains checkbox-related text/classes
                    const elementText = element.textContent.toLowerCase();
                    const elementClass = element.className.toLowerCase();
                    const hasCheckboxIndicators = 
                        elementText.includes('willige ein') ||
                        elementText.includes('einverstanden') ||
                        elementText.includes('akzeptiere') ||
                        elementText.includes('datenschutz') ||
                        elementText.includes('agb') ||
                        elementText.includes('consent') ||
                        elementClass.includes('checkbox') ||
                        elementClass.includes('consent');
                    
                    if (hasCheckboxIndicators && 
                        (targetElement.tagName.toLowerCase() !== 'input' || 
                         (targetElement.type !== 'checkbox' && targetElement.type !== 'radio'))) {{
                        console.log('Element has checkbox indicators, searching more aggressively...');
                        
                        // More aggressive search for associated checkboxes
                        const allInputs = document.querySelectorAll('input[type="checkbox"], input[type="radio"]');
                        for (let input of allInputs) {{
                            // Check if this input is related to the clicked element
                            const inputRect = input.getBoundingClientRect();
                            const elementRect = element.getBoundingClientRect();
                            
                            // Check if they are vertically aligned (same row) or nearby
                            const verticalDistance = Math.abs(inputRect.top - elementRect.top);
                            const horizontalDistance = Math.abs(inputRect.left - elementRect.left);
                            
                            if (verticalDistance <= 50) {{ // Same row
                                targetElement = input;
                                console.log(`Found related ${{input.type}} in same row`);
                                break;
                            }}
                        }}
                    }}
                    
                    return {{
                        tagName: targetElement.tagName.toLowerCase(),
                        type: targetElement.type || '',
                        role: targetElement.getAttribute('role') || '',
                        className: targetElement.className || '',
                        id: targetElement.id || '',
                        name: targetElement.name || '',
                        disabled: targetElement.disabled || false,
                        readonly: targetElement.readOnly || false,
                        multiple: targetElement.multiple || false,
                        value: targetElement.value || '',
                        checked: targetElement.checked || false,
                        selectedValue: targetElement.tagName.toLowerCase() === 'select' ? targetElement.value : '',
                        options: targetElement.tagName.toLowerCase() === 'select' ? 
                            Array.from(targetElement.options).map(opt => ({{
                                value: opt.value,
                                text: opt.text,
                                selected: opt.selected
                            }})) : [],
                        isCustomDropdown: targetElement.classList.contains('custom-select') || 
                                         targetElement.querySelector('.dropdown') !== null ||
                                         targetElement.getAttribute('aria-haspopup') === 'listbox' ||
                                         targetElement.getAttribute('aria-expanded') !== null,
                        isContentEditable: targetElement.contentEditable === 'true',
                        isCheckbox: targetElement.type === 'checkbox' || targetElement.getAttribute('role') === 'checkbox',
                        isRadio: targetElement.type === 'radio' || targetElement.getAttribute('role') === 'radio',
                        hasDataToggle: targetElement.getAttribute('data-toggle') !== null,
                        parentCustomDropdown: !!targetElement.closest('.custom-select, .dropdown, [aria-haspopup="listbox"]'),
                        computedStyle: {{
                            cursor: getComputedStyle(targetElement).cursor,
                            pointerEvents: getComputedStyle(targetElement).pointerEvents
                        }},
                        originalElement: element.tagName.toLowerCase(),
                        wasLabelClicked: wasLabelClicked,
                        originalText: element.textContent.substring(0, 100),
                        targetText: targetElement.textContent ? targetElement.textContent.substring(0, 50) : ''
                    }};
                }}
            """)
            return element_info or {}
        except Exception as e:
            print(f"Error getting element info: {e}")
            return {}
    
    async def handle_native_select(self, x: float, y: float, value: str) -> bool:
        """Handle native HTML select elements"""
        try:
            # Use Playwright's selectOption method for native selects
            result = await self.page.evaluate(f"""
                () => {{
                    const element = document.elementFromPoint({x}, {y});
                    if (!element || element.tagName.toLowerCase() !== 'select') {{
                        return {{ success: false, reason: 'Not a select element' }};
                    }}
                    
                    // Try to find option by value first
                    let option = Array.from(element.options).find(opt => 
                        opt.value === '{value}' || 
                        opt.text.toLowerCase().includes('{value}'.toLowerCase()) ||
                        opt.text.trim() === '{value}' ||
                        opt.value.toLowerCase() === '{value}'.toLowerCase()
                    );
                    
                    if (option) {{
                        element.value = option.value;
                        element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        return {{ success: true, selectedValue: option.value, selectedText: option.text }};
                    }}
                    
                    return {{ success: false, reason: 'Option not found', availableOptions: Array.from(element.options).map(opt => ({{ value: opt.value, text: opt.text }})) }};
                }}
            """)
            
            if result.get('success'):
                print(f"✅ Successfully selected option: {result.get('selectedText')} (value: {result.get('selectedValue')})")
                return True
            else:
                print(f"❌ Failed to select option in native select: {result.get('reason')}")
                if 'availableOptions' in result:
                    print(f"Available options: {result['availableOptions']}")
                return False
                
        except Exception as e:
            print(f"Error handling native select: {e}")
            return False
    
    async def handle_custom_dropdown(self, x: float, y: float, value: str) -> bool:
        """Handle custom dropdown elements (like Bootstrap dropdowns, custom selects, etc.)"""
        try:
            # First click to open dropdown
            await self.page.mouse.click(x, y)
            await asyncio.sleep(0.5)
            
            # Look for dropdown options that appeared
            dropdown_options = await self.page.evaluate(f"""
                () => {{
                    // Common selectors for dropdown options
                    const selectors = [
                        '.dropdown-item',
                        '.custom-select-dropdown-value',
                        '.select-option',
                        '.option',
                        '.dropdown-menu li',
                        '.dropdown-menu a',
                        '[role="option"]',
                        '[data-value]',
                        '.ui-menu-item',
                        '.select2-results__option'
                    ];
                    
                    let options = [];
                    for (let selector of selectors) {{
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {{
                            if (el.offsetParent !== null) {{ // Check if visible
                                const rect = el.getBoundingClientRect();
                                options.push({{
                                    x: rect.left + rect.width / 2,
                                    y: rect.top + rect.height / 2,
                                    text: el.textContent.trim(),
                                    value: el.getAttribute('data-value') || el.textContent.trim(),
                                    element: el
                                }});
                            }}
                        }});
                    }}
                    return options;
                }}
            """)
            
            # Find matching option
            target_option = None
            for option in dropdown_options:
                option_text = option['text'].lower().strip()
                option_value = option['value'].lower().strip()
                search_value = value.lower().strip()
                
                if (option_value == search_value or 
                    option_text == search_value or 
                    search_value in option_text or 
                    option_text in search_value):
                    target_option = option
                    break
            
            if target_option:
                # Click the matching option
                await self.page.mouse.click(target_option['x'], target_option['y'])
                await asyncio.sleep(0.3)
                print(f"✅ Successfully selected custom dropdown option: {target_option['text']}")
                return True
            else:
                print(f"❌ Could not find matching option '{value}' in custom dropdown")
                print(f"Available options: {[opt['text'] for opt in dropdown_options]}")
                # Try to close dropdown by clicking elsewhere
                await self.page.mouse.click(x - 100, y - 100)
                return False
                
        except Exception as e:
            print(f"Error handling custom dropdown: {e}")
            return False
    
    async def handle_searchable_dropdown(self, x: float, y: float, value: str) -> bool:
        """Handle searchable/filterable dropdown elements"""
        try:
            # Click to focus the element
            await self.page.mouse.click(x, y)
            await asyncio.sleep(0.3)
            
            # Try typing to filter options
            await self.page.keyboard.type(value, delay=100)
            await asyncio.sleep(0.5)
            
            # Look for filtered results
            filtered_options = await self.page.evaluate("""
                () => {
                    const selectors = [
                        '.dropdown-item:not(.d-none):not([style*="display: none"])',
                        '.option:not(.hidden)',
                        '[role="option"]:not([aria-hidden="true"])',
                        '.select2-results__option:not([aria-hidden="true"])',
                        '.ui-menu-item:not(.ui-state-disabled)'
                    ];
                    
                    let options = [];
                    for (let selector of selectors) {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {
                            if (el.offsetParent !== null) {
                                const rect = el.getBoundingClientRect();
                                options.push({
                                    x: rect.left + rect.width / 2,
                                    y: rect.top + rect.height / 2,
                                    text: el.textContent.trim()
                                });
                            }
                        });
                    }
                    return options;
                }
            """)
            
            if filtered_options:
                # Click the first filtered result
                first_option = filtered_options[0]
                await self.page.mouse.click(first_option['x'], first_option['y'])
                await asyncio.sleep(0.3)
                print(f"✅ Successfully selected searchable dropdown option: {first_option['text']}")
                return True
            else:
                # Try pressing Enter if no visible options
                await self.page.keyboard.press('Enter')
                await asyncio.sleep(0.3)
                print(f"✅ Attempted to select searchable dropdown by pressing Enter")
                return True
                
        except Exception as e:
            print(f"Error handling searchable dropdown: {e}")
            return False
    
    async def handle_text_input(self, x: float, y: float, value: str) -> bool:
        """Handle regular text input fields"""
        try:
            # Click to focus
            await self.page.mouse.click(x, y, delay=100)
            await asyncio.sleep(0.5)
            
            # Clear existing content
            await self.page.mouse.click(x, y, click_count=3)  # Triple click to select all
            await asyncio.sleep(0.2)
            
            # Type new value
            await self.page.keyboard.type(value, delay=50)
            await asyncio.sleep(0.3)
            
            # Trigger change events
            await self.page.keyboard.press('Tab')
            await asyncio.sleep(0.2)
            
            print(f"✅ Successfully filled text input with: {value}")
            return True
            
        except Exception as e:
            print(f"Error handling text input: {e}")
            return False
    
    async def handle_contenteditable(self, x: float, y: float, value: str) -> bool:
        """Handle contenteditable elements"""
        try:
            await self.page.mouse.click(x, y)
            await asyncio.sleep(0.3)
            
            # Select all existing content
            await self.page.keyboard.press(self.select_all)
            await asyncio.sleep(0.1)
            
            # Type new content
            await self.page.keyboard.type(value, delay=50)
            await asyncio.sleep(0.3)
            
            print(f"✅ Successfully filled contenteditable with: {value}")
            return True
            
        except Exception as e:
            print(f"Error handling contenteditable: {e}")
            return False
    
    async def handle_checkbox_radio(self, x: float, y: float, value: str, element_info: Dict[str, Any]) -> bool:
        """Handle checkbox and radio button elements"""
        try:
            current_checked = element_info.get('checked', False)
            is_checkbox = element_info.get('isCheckbox', False)
            is_radio = element_info.get('isRadio', False)
            
            # Determine desired state based on value
            # Common ways to indicate "checked": "true", "1", "yes", "on", "checked"
            should_be_checked = str(value).lower() in ['true', '1', 'yes', 'on', 'checked', 'check', 'accept', 'agree']
            
            print(f"🔲 {'Checkbox' if is_checkbox else 'Radio'} - Current: {current_checked}, Target: {should_be_checked}")
            
            # Only click if we need to change the state
            if current_checked != should_be_checked:
                # If we clicked on a label, find the actual checkbox/radio coordinates
                if element_info.get('wasLabelClicked'):
                    # Get the actual checkbox/radio coordinates
                    checkbox_coords = await self.page.evaluate(f"""
                        () => {{
                            const element = document.elementFromPoint({x}, {y});
                            if (!element) return null;
                            
                            let targetElement = element;
                            if (element.tagName.toLowerCase() === 'label') {{
                                const forAttr = element.getAttribute('for');
                                if (forAttr) {{
                                    targetElement = document.getElementById(forAttr);
                                }} else {{
                                    const inputInLabel = element.querySelector('input[type="checkbox"], input[type="radio"]');
                                    if (inputInLabel) {{
                                        targetElement = inputInLabel;
                                    }}
                                }}
                            }}
                            
                            if (targetElement && (targetElement.type === 'checkbox' || targetElement.type === 'radio')) {{
                                const rect = targetElement.getBoundingClientRect();
                                return {{
                                    x: rect.left + rect.width / 2,
                                    y: rect.top + rect.height / 2
                                }};
                            }}
                            return null;
                        }}
                    """)
                    
                    if checkbox_coords:
                        await self.page.mouse.click(checkbox_coords['x'], checkbox_coords['y'])
                    else:
                        await self.page.mouse.click(x, y)
                else:
                    await self.page.mouse.click(x, y)
                    
                await asyncio.sleep(0.3)
                print(f"✅ Successfully {'checked' if should_be_checked else 'unchecked'} {'checkbox' if is_checkbox else 'radio button'}")
            else:
                print(f"ℹ️ {'Checkbox' if is_checkbox else 'Radio'} already in desired state")
            
            return True
            
        except Exception as e:
            print(f"Error handling {'checkbox' if element_info.get('isCheckbox') else 'radio'}: {e}")
            return False
    
    async def fill_element(self, element_data: Dict[str, Any]) -> bool:
        """Main method to fill an element based on its type"""
        x = element_data.get("x")
        y = element_data.get("y")
        value = element_data.get("text_input")
        
        if not all([x is not None, y is not None, value is not None]):
            print(f"❌ Missing required data: x={x}, y={y}, value={value}")
            return False
        
        # Get detailed element information
        element_info = await self.get_element_info(x, y)
        if not element_info:
            print(f"❌ Could not get element information for coordinates ({x}, {y})")
            return False
        
        tag_name = element_info.get('tagName', '').lower()
        element_type = element_info.get('type', '').lower()
        
        print(f"🔍 Handling element: {tag_name} (type: {element_type}) at ({x}, {y}) with value: '{value}'")
        print(f"🔍 Element details: isCheckbox={element_info.get('isCheckbox')}, isRadio={element_info.get('isRadio')}, originalElement={element_info.get('originalElement')}")
        
        # Handle different element types
        if tag_name == 'select':
            print("📋 Detected native select element")
            return await self.handle_native_select(x, y, value)
        
        elif element_info.get('isCheckbox') or element_info.get('isRadio'):
            print("🔲 Detected checkbox/radio element")
            return await self.handle_checkbox_radio(x, y, value, element_info)
        
        elif element_info.get('isCustomDropdown') or element_info.get('parentCustomDropdown'):
            print("📋 Detected custom dropdown element")
            return await self.handle_custom_dropdown(x, y, value)
        
        elif element_info.get('isContentEditable'):
            print("📝 Detected contenteditable element")
            return await self.handle_contenteditable(x, y, value)
        
        elif (tag_name == 'input' and element_type in ['search', 'text'] and 
              any(keyword in element_info.get('className', '').lower() for keyword in ['search', 'filter', 'autocomplete'])):
            print("🔍 Detected searchable input element")
            return await self.handle_searchable_dropdown(x, y, value)
        
        elif tag_name in ['input', 'textarea']:
            print("📝 Detected text input element")
            return await self.handle_text_input(x, y, value)
        
        else:
            print(f"❓ Unknown element type, attempting text input fallback")
            return await self.handle_text_input(x, y, value)

# Enhanced fill_fields function
async def enhanced_fill_fields(elements_input: List[Dict[str, Any]], page: Page) -> Page:
    """Enhanced field filling with improved dropdown support"""
    handler = EnhancedInputHandler(page)
    
    print(f"🚀 Starting enhanced fill operation for {len(elements_input)} elements")
    
    successful_fills = 0
    for i, element in enumerate(elements_input):
        print(f"\n--- Processing element {i+1}/{len(elements_input)} ---")
        
        try:
            success = await handler.fill_element(element)
            if success:
                successful_fills += 1
            else:
                print(f"⚠️ Failed to fill element {i+1}")
                
        except Exception as e:
            print(f"❌ Exception while filling element {i+1}: {e}")
    
    print(f"\n✅ Enhanced fill operation completed: {successful_fills}/{len(elements_input)} elements filled successfully")
    return page


# Enhanced cross-reference function with element type detection
def enhanced_cross_reference(elements_list: List[Dict], agent_response: Dict) -> tuple:
    """Enhanced cross-reference with better element classification"""
    elements_click = []
    elements_input = []
    
    if "click" in agent_response and agent_response['click'] != -1:
        for element in elements_list:
            if str(element['id']) == str(agent_response['click']):
                elements_click.append(element)
                break
    
    if "write" in agent_response and len(agent_response['write']) > 0:
        input_mapping = {str(item[0]): item[1] for item in agent_response['write']}
        
        for element in elements_list:
            element_id = str(element['id'])
            if element_id in input_mapping:
                # Create enhanced element data
                enhanced_element = element.copy()
                enhanced_element["text_input"] = input_mapping[element_id]
                
                # Add element type hints based on available data
                tag = element.get('tag', '').lower()
                type_attr = element.get('typeAttr', '').lower()
                class_attr = element.get('classAttr', '').lower()
                
                enhanced_element['element_hints'] = {
                    'is_select': tag == 'select',
                    'is_checkbox': element.get('typeAttr', '').lower() == 'checkbox' or 
                                  'checkbox' in class_attr,
                    'is_radio': element.get('typeAttr', '').lower() == 'radio' or 
                               'radio' in class_attr,
                    'is_custom_dropdown': any(keyword in class_attr for keyword in 
                        ['dropdown', 'select', 'picker', 'combobox']),
                    'is_searchable': any(keyword in class_attr for keyword in 
                        ['search', 'filter', 'autocomplete', 'typeahead']),
                    'is_contenteditable': 'contenteditable' in element.get('text', '').lower()
                }
                
                elements_input.append(enhanced_element)
    
    return elements_click, elements_input

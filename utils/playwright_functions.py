import asyncio
from typing import List, Dict, Any
from playwright.async_api import Page
import platform
from typing import List, Dict, Any
from typing import List, Dict, Any
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

### takes current page as input and performs action, returns page 

def cross_reference (elements_list , agent_response):
    elements_click=[]
    elements_input=[]
    if("click" in agent_response):     
        if(agent_response['click']!=-1):
            for i in elements_list :
                if (str(i['id'])==str(agent_response['click'])):
                    elements_click.append(i)
                    break  # Only add the first matching element to prevent duplicates

    if("write" in agent_response):
        list_of_ids = {}
        for i in agent_response['write'] :
            list_of_ids[i[0]]=i[1]

        if(len(agent_response['write'])!=0):
            for i in elements_list : 
                if(str(i['id']) in list_of_ids):
                    #elements list me i ek json hai
                    i["text_input"] = list_of_ids[str(i['id'])]
                   
                    elements_input.append(i)
                    
    # Elements input is a list of json

    
    return elements_click, elements_input
    ##### add some logs here as well


def detect_element_type(element_data: Dict[str, Any]) -> str:
    """
    Detect the type of element to determine the best input strategy.
    Returns: 'select', 'custom_dropdown', 'searchable', 'contenteditable', 'text_input'
    """
    tag = element_data.get('tag', '').lower()
    type_attr = element_data.get('typeAttr', '').lower()
    class_attr = element_data.get('classAttr', '').lower()
    text_content = element_data.get('text', '').lower()
    
    # Native select elements
    if tag == 'select':
        return 'select'
    
    # Custom dropdown indicators
    dropdown_classes = ['dropdown', 'select', 'picker', 'combobox', 'custom-select']
    if any(cls in class_attr for cls in dropdown_classes):
        return 'custom_dropdown'
    
    # Searchable/filterable inputs
    searchable_classes = ['search', 'filter', 'autocomplete', 'typeahead']
    if tag == 'input' and (type_attr in ['search', 'text'] and 
                          any(cls in class_attr for cls in searchable_classes)):
        return 'searchable'
    
    # Content editable elements
    if 'contenteditable' in text_content or tag in ['div', 'span'] and 'editable' in class_attr:
        return 'contenteditable'
    
    # Default to text input
    return 'text_input' 


### trying popup detect for click , controlled example
async def click(
    elements_click: List[Dict[str, Any]],
    page: Page
) -> Page:
    
    # Only click the first element to avoid duplicate clicks
    if elements_click:
        el = elements_click[0]  # Only take the first element
        x = el.get("x")
        y = el.get("y")
        if x is not None and y is not None:
            # 🔍 Start listening for a popup before clicking
            popup_task = page.wait_for_event("popup", timeout=5000)

            # Trigger the click that *may* open a popup
            await page.mouse.click(x, y)

            # Try to capture the popup
            try:
                popup = await popup_task
                print("Redirect detecting, shifting to New Tab")
            except :
                popup = None
                print("No redirects detected")

            if popup is not None:
                # ✔ If a popup appeared, switch to it
                page = popup
                print("Changed to new tab successfully")

    return page

async def write(elements_input: List[Any], page: Page) -> Page:
    import platform
    select_all = "Meta+A" if platform.system() == "Darwin" else "Control+A"

    for item in elements_input:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            el, text = item
        else:
            el = item
            text = el.get("value")

        x = el.get("x")
        y = el.get("y")
        if x is None or y is None or text is None:
            continue

        # More robust focus and clear approach
        await page.mouse.click(x, y, delay=100)
        await asyncio.sleep(0.5)  # Wait for focus to settle
        
        # Try multiple approaches to ensure field is focused and cleared
        try:
            # First try to focus the element by coordinates
            await page.mouse.click(x, y)
            await asyncio.sleep(0.3)
            
            # Try triple-click to select all text in the field
            await page.mouse.click(x, y, click_count=3)
            await asyncio.sleep(0.2)
            
            # Type the new text (this will replace selected text)
            await page.keyboard.type(text, delay=50)
            
        except Exception as e:
            print(f"Error with triple-click approach, trying fallback: {e}")
            # Fallback: use keyboard shortcuts only if we're confident about focus
            try:
                await page.mouse.click(x, y)
                await asyncio.sleep(0.5)
                await page.keyboard.press(select_all)
                await page.keyboard.press("Backspace")
                await page.keyboard.type(text, delay=50)
            except Exception as e2:
                print(f"Fallback also failed: {e2}")
                # Last resort: just type without clearing (might append)
                await page.keyboard.type(text, delay=50)

    return page

async def handle_select_element(page: Page, x: float, y: float, value: str) -> bool:
    """Handle native HTML select elements with improved option matching"""
    try:
        result = await page.evaluate(f"""
            () => {{
                const element = document.elementFromPoint({x}, {y});
                if (!element || element.tagName.toLowerCase() !== 'select') {{
                    return {{ success: false, reason: 'Not a select element' }};
                }}
                
                // Get all options
                const options = Array.from(element.options);
                const searchValue = '{value}'.toLowerCase().trim();
                
                // Try multiple matching strategies
                let matchedOption = null;
                
                // 1. Exact value match
                matchedOption = options.find(opt => opt.value.toLowerCase() === searchValue);
                
                // 2. Exact text match
                if (!matchedOption) {{
                    matchedOption = options.find(opt => opt.text.toLowerCase().trim() === searchValue);
                }}
                
                // 3. Text contains search value
                if (!matchedOption) {{
                    matchedOption = options.find(opt => opt.text.toLowerCase().includes(searchValue));
                }}
                
                // 4. Search value contains text (for abbreviations)
                if (!matchedOption) {{
                    matchedOption = options.find(opt => searchValue.includes(opt.text.toLowerCase().trim()));
                }}
                
                // 5. Partial word match
                if (!matchedOption) {{
                    const searchWords = searchValue.split(/\\s+/);
                    matchedOption = options.find(opt => 
                        searchWords.some(word => 
                            opt.text.toLowerCase().includes(word) || opt.value.toLowerCase().includes(word)
                        )
                    );
                }}
                
                if (matchedOption) {{
                    element.value = matchedOption.value;
                    
                    // Trigger events
                    element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    element.focus();
                    element.blur();
                    
                    return {{ 
                        success: true, 
                        selectedValue: matchedOption.value, 
                        selectedText: matchedOption.text 
                    }};
                }}
                
                return {{ 
                    success: false, 
                    reason: 'No matching option found',
                    availableOptions: options.map(opt => ({{ value: opt.value, text: opt.text }}))
                }};
            }}
        """)
        
        if result.get('success'):
            print(f"✅ Selected option: {result.get('selectedText')} (value: {result.get('selectedValue')})")
            return True
        else:
            print(f"❌ Failed to select option: {result.get('reason')}")
            if 'availableOptions' in result:
                options_preview = [f"{opt['text']} ({opt['value']})" for opt in result['availableOptions'][:5]]
                print(f"Available options: {options_preview}")
            return False
            
    except Exception as e:
        print(f"Error handling select element: {e}")
        return False


async def handle_custom_dropdown(page: Page, x: float, y: float, value: str) -> bool:
    """Handle custom dropdown elements with improved detection and interaction"""
    try:
        # First click to open dropdown
        await page.mouse.click(x, y)
        await asyncio.sleep(0.8)  # Longer wait for animation
        
        # Enhanced dropdown option detection
        dropdown_options = await page.evaluate(f"""
            () => {{
                const searchValue = '{value}'.toLowerCase().trim();
                
                // Comprehensive list of dropdown option selectors
                const selectors = [
                    '.dropdown-item',
                    '.dropdown-option', 
                    '.custom-select-dropdown-value',
                    '.select-option',
                    '.option',
                    '.dropdown-menu li',
                    '.dropdown-menu a',
                    '.dropdown-content li',
                    '.dropdown-content a',
                    '[role="option"]',
                    '[data-value]',
                    '.ui-menu-item',
                    '.select2-results__option',
                    '.chosen-results li',
                    '.selectize-dropdown-content .option',
                    '.vs__dropdown-option',
                    '.multiselect__option',
                    '.el-select-dropdown__item'
                ];
                
                let allOptions = [];
                
                for (let selector of selectors) {{
                    try {{
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {{
                            // Check if element is visible and interactable
                            const rect = el.getBoundingClientRect();
                            const style = window.getComputedStyle(el);
                            
                            if (rect.width > 0 && rect.height > 0 && 
                                style.display !== 'none' && 
                                style.visibility !== 'hidden' &&
                                style.opacity !== '0') {{
                                
                                const text = el.textContent.trim();
                                const value = el.getAttribute('data-value') || 
                                             el.getAttribute('value') || 
                                             text;
                                             
                                if (text.length > 0) {{
                                    allOptions.push({{
                                        x: rect.left + rect.width / 2,
                                        y: rect.top + rect.height / 2,
                                        text: text,
                                        value: value,
                                        selector: selector,
                                        element: el
                                    }});
                                }}
                            }}
                        }});
                    }} catch(e) {{
                        console.log('Error with selector:', selector, e);
                    }}
                }}
                
                // Remove duplicates based on position and text
                const uniqueOptions = [];
                const seen = new Set();
                
                for (let option of allOptions) {{
                    const key = `${{option.x}}-${{option.y}}-${{option.text}}`;
                    if (!seen.has(key)) {{
                        seen.add(key);
                        uniqueOptions.push(option);
                    }}
                }}
                
                return uniqueOptions;
            }}
        """)
        
        if not dropdown_options:
            print("❌ No dropdown options found")
            # Try to close dropdown by pressing Escape
            await page.keyboard.press('Escape')
            return False
        
        print(f"🔍 Found {len(dropdown_options)} dropdown options")
        
        # Enhanced option matching
        def calculate_match_score(option_text: str, search_value: str) -> float:
            option_lower = option_text.lower().strip()
            search_lower = search_value.lower().strip()
            
            # Exact match
            if option_lower == search_lower:
                return 100
            
            # Contains match
            if search_lower in option_lower:
                return 80
            
            # Reverse contains (search contains option)
            if option_lower in search_lower:
                return 70
            
            # Word match
            option_words = option_lower.split()
            search_words = search_lower.split()
            word_matches = sum(1 for word in search_words if any(word in opt_word for opt_word in option_words))
            if word_matches > 0:
                return 60 + (word_matches * 10)
            
            # Character similarity (basic)
            common_chars = sum(1 for char in search_lower if char in option_lower)
            return (common_chars / max(len(search_lower), len(option_lower))) * 50
        
        # Find best matching option
        best_option = None
        best_score = 0
        
        for option in dropdown_options:
            score = calculate_match_score(option['text'], value)
            if score > best_score and score > 40:  # Minimum threshold
                best_score = score
                best_option = option
        
        if best_option:
            print(f"🎯 Best match: '{best_option['text']}' (score: {best_score})")
            await page.mouse.click(best_option['x'], best_option['y'])
            await asyncio.sleep(0.5)
            print(f"✅ Successfully selected custom dropdown option")
            return True
        else:
            print(f"❌ No suitable match found for '{value}'")
            print(f"Available options: {[opt['text'] for opt in dropdown_options[:10]]}")
            # Try to close dropdown
            await page.keyboard.press('Escape')
            return False
            
    except Exception as e:
        print(f"Error handling custom dropdown: {e}")
        return False


async def handle_searchable_input(page: Page, x: float, y: float, value: str) -> bool:
    """Handle searchable/filterable input elements"""
    try:
        # Focus the input
        await page.mouse.click(x, y)
        await asyncio.sleep(0.3)
        
        # Clear existing content
        await page.keyboard.press("Control+a" if platform.system() != "Darwin" else "Meta+a")
        await asyncio.sleep(0.1)
        
        # Type search value
        await page.keyboard.type(value, delay=100)
        await asyncio.sleep(1.0)  # Wait for search results
        
        # Look for suggestions/results
        suggestions = await page.evaluate("""
            () => {
                const selectors = [
                    '.autocomplete-suggestion',
                    '.search-suggestion', 
                    '.typeahead-suggestion',
                    '.ui-autocomplete li',
                    '.dropdown-item:not(.d-none)',
                    '.suggestion',
                    '[role="option"]'
                ];
                
                let results = [];
                for (let selector of selectors) {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            results.push({
                                x: rect.left + rect.width / 2,
                                y: rect.top + rect.height / 2,
                                text: el.textContent.trim()
                            });
                        }
                    });
                }
                return results;
            }
        """)
        
        if suggestions and len(suggestions) > 0:
            # Click first suggestion
            first_suggestion = suggestions[0]
            await page.mouse.click(first_suggestion['x'], first_suggestion['y'])
            await asyncio.sleep(0.3)
            print(f"✅ Selected search suggestion: {first_suggestion['text']}")
            return True
        else:
            # No suggestions, just press Enter
            await page.keyboard.press('Enter')
            await asyncio.sleep(0.3)
            print(f"✅ Entered search value and pressed Enter")
            return True
            
    except Exception as e:
        print(f"Error handling searchable input: {e}")
        return False


async def enhanced_fill_fields(elements_input: List[Dict[str, Any]], page: Page) -> Page:
    """Enhanced field filling with improved dropdown and input handling"""
    select_all = "Meta+A" if platform.system() == "Darwin" else "Control+A"
    
    print(f"🚀 Starting enhanced fill operation for {len(elements_input)} elements")
    
    successful_fills = 0
    
    for i, el in enumerate(elements_input):
        x, y = el.get("x"), el.get("y")
        in_text = el.get("text_input")
        
        if x is None or y is None or in_text is None:
            print(f"❌ Element {i+1}: Missing required data")
            continue
        
        print(f"\n--- Processing element {i+1}/{len(elements_input)} ---")
        print(f"🎯 Target: ({x}, {y}) with value: '{in_text}'")
        
        # Detect element type
        element_type = detect_element_type(el)
        print(f"🔍 Detected element type: {element_type}")
        
        success = False
        
        try:
            if element_type == 'select':
                success = await handle_select_element(page, x, y, in_text)
            elif element_type == 'custom_dropdown':
                success = await handle_custom_dropdown(page, x, y, in_text)
            elif element_type == 'searchable':
                success = await handle_searchable_input(page, x, y, in_text)
            else:
                # Default text input handling with improvements
                success = await handle_text_input_enhanced(page, x, y, in_text, select_all)
            
            if success:
                successful_fills += 1
            else:
                print(f"⚠️ Failed to fill element {i+1}, trying fallback method")
                # Fallback to basic text input
                success = await handle_text_input_enhanced(page, x, y, in_text, select_all)
                if success:
                    successful_fills += 1
                    
        except Exception as e:
            print(f"❌ Exception while filling element {i+1}: {e}")
    
    print(f"\n✅ Enhanced fill operation completed: {successful_fills}/{len(elements_input)} elements filled successfully")
    return page


async def handle_text_input_enhanced(page: Page, x: float, y: float, text: str, select_all: str) -> bool:
    """Enhanced text input handling with better error recovery"""
    try:
        # Multiple click and focus attempts
        await page.mouse.click(x, y, delay=100)
        await asyncio.sleep(0.5)
        
        # Try triple-click to select all
        await page.mouse.click(x, y, click_count=3)
        await asyncio.sleep(0.2)
        
        # Type the text
        await page.keyboard.type(text, delay=50)
        await asyncio.sleep(0.3)
        
        # Trigger change events
        await page.keyboard.press('Tab')
        await page.keyboard.press('Shift+Tab')  # Return focus
        await asyncio.sleep(0.2)
        
        print(f"✅ Successfully filled text input")
        return True
        
    except Exception as e:
        print(f"❌ Enhanced text input failed: {e}")
        
        # Fallback method
        try:
            await page.mouse.click(x, y)
            await asyncio.sleep(0.5)
            await page.keyboard.press(select_all)
            await page.keyboard.press("Backspace")
            await page.keyboard.type(text, delay=50)
            print(f"✅ Fallback text input succeeded")
            return True
        except Exception as e2:
            print(f"❌ Fallback also failed: {e2}")
            return False



async def fill_fields(
    elements_input ,
    page: Page
) -> Page:
    """Backward compatibility wrapper - now uses enhanced filling"""
    # Import the better enhanced handler from the dedicated module
    from .enhanced_input_handler import enhanced_fill_fields as enhanced_handler
    return await enhanced_handler(elements_input, page)


async def handle_new_tab(page):
    """
    If page.context has more than one page, 
    find the new one, close the old, and return the new.
    """
    context = page.context
    pages = context.pages
    if len(pages) > 1:
        # assume the new page is the one that's not 'page'
        new_page = next(p for p in pages if p is not page)
        
        # wait for it to fully load
        await new_page.wait_for_load_state('load')
        # bring it to front (optional, in headed mode)
        await new_page.bring_to_front()
        
        # close the original
        await page.close()
        
        return new_page
    return page


async def scroll(vericomm_output , page):
    if(vericomm_output["scroll_up_down"]==-1):
        return page
    elif (vericomm_output["scroll_up_down"]==1):
        await page.evaluate("window.scrollBy(0, -200)")
    elif (vericomm_output["scroll_up_down"]==2):
        await page.evaluate("window.scrollBy(0, 200)")
    return page 

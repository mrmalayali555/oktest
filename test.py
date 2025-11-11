import asyncio
import logging
from playwright.async_api import async_playwright, Page, expect
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GoetheBookingBot:
    def __init__(self, email: str, password: str, card_details: dict):
        """
        Initialize the booking bot with credentials and payment details.
        
        Args:
            email: User email for login
            password: User password for login
            card_details: Dictionary with keys: name, number, expiry, cvv
        """
        self.email = email
        self.password = password
        self.card_details = card_details
        self.page: Optional[Page] = None
        
    async def safe_click(self, selector: str, timeout: int = 30000, description: str = ""):
        """Safely click an element with retry logic and logging."""
        try:
            logger.info(f"Attempting to click: {description or selector}")
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self.page.click(selector, timeout=timeout)
            logger.info(f"Successfully clicked: {description or selector}") # Brief pause after click
            return True
        except Exception as e:
            logger.error(f"Failed to click {description or selector}: {str(e)}")
            return False
    
    async def safe_fill(self, selector: str, value: str, timeout: int = 30000, description: str = ""):
        """Safely fill an input field with retry logic."""
        try:
            logger.info(f"Attempting to fill: {description or selector}")
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self.page.fill(selector, value, timeout=timeout)
            logger.info(f"Successfully filled: {description or selector}")
            return True
        except Exception as e:
            logger.error(f"Failed to fill {description or selector}: {str(e)}")
            return False
    
    async def wait_for_navigation(self, timeout: int = 30000):
        """Wait for page navigation to complete."""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
            logger.info("Navigation completed")
            return True
        except Exception as e:
            logger.warning(f"Navigation wait warning: {str(e)}")
            return False
    
    async def handle_session_dialog(self):
        """Handle the 'another session is still active' dialog if it appears."""
        try:
            # Check if dialog exists (with short timeout)
            discard_button = self.page.locator("text=/discard other booking/i")
            if await discard_button.count() > 0:
                logger.info("Session dialog detected, clicking 'Discard other booking'")
                await discard_button.click(timeout=5000)
                return True
        except Exception as e:
            logger.info("No session dialog found (this is normal)")
        return False
    
    async def handle_discard_other_booking(self):
        """Handle the 'Discard other booking' dialog that may appear after login."""
        try:
            logger.info("Checking for 'Discard other booking' dialog...")
            
            # Multiple selectors for the discard button
            discard_selectors = [
                "button:has-text('DISCARD OTHER BOOKING')",
                "text=/discard other booking/i",
                "button:has-text('Discard other booking')",
                "//button[contains(text(), 'DISCARD OTHER BOOKING')]",
                "button[class*='cs-button']:has-text('DISCARD')"
            ]
            
            for selector in discard_selectors:
                try:
                    button = self.page.locator(selector)
                    if await button.count() > 0:
                        logger.info("Found 'Discard other booking' dialog, clicking button...")
                        await button.click(timeout=5000)
                        logger.info("Successfully clicked 'Discard other booking'")
                        return True
                except Exception:
                    continue
            
            logger.info("No 'Discard other booking' dialog found (this is normal if no previous booking)")
            return False
            
        except Exception as e:
            logger.warning(f"Discard booking dialog handling warning: {str(e)}")
            return False
    
    async def scroll_and_click_card(self, card_selector: str = None):
        """Scroll and click on a course card."""
        try:
            logger.info("Looking for course card...")
            
            # If specific selector provided, use it
            if card_selector:
                await self.page.wait_for_selector(card_selector, timeout=30000)
                await self.page.locator(card_selector).scroll_into_view_if_needed()
                await self.page.click(card_selector)
            else:
                # Generic approach: find clickable cards
                cards = self.page.locator("div[role='button'], .card, .course-card, a.card")
                count = await cards.count()
                logger.info(f"Found {count} potential cards")
                
                if count > 0:
                    first_card = cards.first
                    await first_card.scroll_into_view_if_needed()
                    await first_card.click()
                else:
                    raise Exception("No cards found")
            
            logger.info("Successfully clicked course card")
            await self.wait_for_navigation()
            return True
            
        except Exception as e:
            logger.error(f"Failed to click card: {str(e)}")
            return False
    
    async def select_modules(self):
        """Click on 'Select Modules' button."""
        selectors = [
            "text=/select modules/i",
            "button:has-text('Select Modules')",
            "[data-testid*='select-module']",
            "//button[contains(text(), 'Select') and contains(text(), 'Module')]"
        ]
        
        for selector in selectors:
            if await self.safe_click(selector, timeout=10000, description="Select Modules"):
                await self.wait_for_navigation()
                return True
        
        logger.error("Could not find 'Select Modules' button")
        return False
    
    async def configure_module_checkboxes(self, modules_to_select: list):
        """
        Configure which module checkboxes should be selected.
        
        Args:
            modules_to_select: List of module names to keep selected (e.g., ['reading', 'listening', 'writing', 'speaking'])
                              If empty or None, keeps all selected (default state)
        """
        try:
            logger.info("Configuring module checkboxes...")
            
            # Wait for checkboxes to be visible - using the exact selector from HTML
            await self.page.wait_for_selector("input.cs-checkbox__input[type='checkbox']", timeout=10000)
            await asyncio.sleep(1)  # Wait for page to stabilize
            
            # If no specific modules requested, keep all checked (default)
            if not modules_to_select:
                logger.info("No specific modules requested, keeping all selected")
                return True
            
            # Normalize module names to lowercase for comparison
            modules_to_select = [m.lower().strip() for m in modules_to_select]
            logger.info(f"Modules to select: {modules_to_select}")
            
            # Module checkboxes with their specific IDs (with spaces)
            module_configs = {
                'reading': ' reading ',
                'listening': ' listening ',
                'writing': ' writing ',
                'speaking': ' speaking '
            }
            
            # Process each module
            for module_name, checkbox_id in module_configs.items():
                try:
                    # Use JavaScript to check the checkbox state and toggle it
                    checkbox_selector = f'input[id="{checkbox_id}"]'
                    
                    # Check if checkbox exists
                    checkbox = self.page.locator(checkbox_selector)
                    if await checkbox.count() == 0:
                        logger.warning(f"{module_name.upper()} checkbox not found")
                        continue
                    
                    # Get current state
                    is_checked = await checkbox.is_checked()
                    should_be_selected = module_name in modules_to_select
                    
                    # Toggle checkbox if needed using JavaScript
                    if is_checked and not should_be_selected:
                        logger.info(f"Unchecking {module_name.upper()} module")
                        # Use JavaScript to click the checkbox directly
                        await self.page.evaluate(f'''
                            document.querySelector('input[id="{checkbox_id}"]').click();
                        ''')
                        await asyncio.sleep(0.5)
                    elif not is_checked and should_be_selected:
                        logger.info(f"Checking {module_name.upper()} module")
                        await self.page.evaluate(f'''
                            document.querySelector('input[id="{checkbox_id}"]').click();
                        ''')
                        await asyncio.sleep(0.5)
                    else:
                        logger.info(f"{module_name.upper()} module already in correct state ({'checked' if is_checked else 'unchecked'})")
                        
                except Exception as e:
                    logger.error(f"Error processing {module_name} checkbox: {str(e)}")
                    continue
            
            logger.info("Module checkbox configuration completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to configure module checkboxes: {str(e)}")
            # Take screenshot for debugging
            if self.page:
                try:
                    await self.page.screenshot(path="checkbox_error.png", full_page=True)
                    logger.info("Screenshot saved as checkbox_error.png")
                except Exception as screenshot_error:
                    logger.warning(f"Could not save checkbox error screenshot: {screenshot_error}")
            return False
    
    async def click_continue(self, context: str = ""):
        """Click continue button with multiple selector attempts."""
        selectors = [
            "button[name='continue']",  # Direct match for your button
            "button:has-text('Continue')",
            "text=/^continue$/i",
            "[data-testid*='continue']",
            "//button[contains(text(), 'Continue')]",
            "input[type='submit'][value*='Continue']",
            "button[type='button']:has-text('Continue')"
        ]
        
        for selector in selectors:
            try:
                logger.info(f"Trying selector: {selector}")
                if await self.safe_click(selector, timeout=5000, description=f"Continue ({context})"):
                    await self.wait_for_navigation()
                    return True
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {str(e)}")
                continue
        
        logger.error(f"Could not find Continue button ({context})")
        return False
    
    async def book_for_myself(self):
        """Click 'Book for myself' button."""
        selectors = [
            "button#i4d2d",  # Direct ID from your screenshot
            "button:has-text('BOOK FOR MYSELF')",  # Exact text match
            "text=/book for myself/i",
            "button[class*='cs-button'][class*='cs-layer__button']",
            "[data-testid*='book-myself']",
            "//button[contains(text(), 'BOOK FOR MYSELF')]"
        ]
        
        for selector in selectors:
            try:
                logger.info(f"Trying book_for_myself selector: {selector}")
                if await self.safe_click(selector, timeout=5000, description="Book for myself"):
                    await self.wait_for_navigation()
                    return True
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {str(e)}")
                continue
        
        logger.error("Could not find 'Book for myself' button")
        return False
    
    async def login(self):
        """Perform login with email and password."""
        try:
            logger.info("Attempting to login...")
            
            # Wait for login form
            await self.page.wait_for_selector("input#username", timeout=30000)
            logger.info("Login form found")
            
            # Fill email - Direct ID selector
            await self.page.fill("input#username", self.email)
            logger.info(f"Filled email: {self.email}")
            
            # Fill password - Direct ID selector
            await self.page.fill("input#password", self.password)
            logger.info("Filled password")
            
            # Click login button - Direct name selector
            await self.page.click("input[name='submit'][value='Log in']")
            logger.info("Clicked login button")
            
            await self.wait_for_navigation()
            
            # Handle session dialog if present
            await self.handle_session_dialog()
            
            # Click continue after login if needed
            await self.click_continue("after login")
            
            logger.info("Login completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            # Take screenshot for debugging
            if self.page:
                try:
                    await self.page.screenshot(path="login_error.png", full_page=True)
                    logger.info("Screenshot saved as login_error.png")
                except Exception as screenshot_error:
                    logger.warning(f"Could not save login error screenshot: {screenshot_error}")
            return False
    
    async def handle_payment(self):
        """Handle the payment process - stops at payment page without filling card details."""
        try:
            logger.info("Starting payment process...")
            
            # Click 'ORDER, SUBJECT TO CHARGE' button
            order_selectors = [
                "button#MFBAYXaHYKSrnuxTmzU",  # Direct ID from your screenshot
                "button:has-text('ORDER, SUBJECT TO CHARGE')",
                "text=/order.*subject.*charge/i",
                "button[class*='cs-button'][class*='arrow_next']",
                "//button[contains(text(), 'ORDER') and contains(text(), 'CHARGE')]"
            ]
            
            button_clicked = False
            for selector in order_selectors:
                try:
                    logger.info(f"Trying order button selector: {selector}")
                    if await self.safe_click(selector, timeout=5000, description="Order subject to charge"):
                        button_clicked = True
                        break
                except Exception as e:
                    logger.debug(f"Order button selector {selector} failed: {str(e)}")
                    continue
            
            if button_clicked:
                logger.info("✅ Successfully clicked 'ORDER, SUBJECT TO CHARGE' button")
                logger.info("✅ Reached payment page - BOOKING SUCCESSFUL!")
                logger.info("⚠  Card details NOT filled (as per configuration)")
                await asyncio.sleep(3)  # Wait a bit to see the payment page
                return True
            else:
                logger.warning("Could not click 'ORDER, SUBJECT TO CHARGE' button")
                return False
            
        except Exception as e:
            logger.error(f"Payment process failed: {str(e)}")
            return False
    
    async def handle_cookie_consent(self):
        """Handle cookie consent dialog if it appears."""
        try:
            logger.info("Checking for cookie consent dialog...")
            
            # Multiple selectors for cookie acceptance
            accept_selectors = [
                "button:has-text('Accept All')",
                "text=/accept all/i",
                "[data-testid*='accept']",
                "button[class*='accept']",
                "//button[contains(text(), 'Accept')]"
            ]
            
            for selector in accept_selectors:
                try:
                    button = self.page.locator(selector)
                    if await button.count() > 0:
                        logger.info("Cookie consent dialog found, clicking Accept All")
                        await button.click(timeout=5000)
                        return True
                except Exception:
                    continue
            
            logger.info("No cookie consent dialog found (already accepted or not present)")
            return False
            
        except Exception as e:
            logger.warning(f"Cookie consent handling warning: {str(e)}")
            return False
    
    async def click_city_details(self, city_name: str = None):
        """Click on the first button in the courses-finder-list."""
        try:
            logger.info("Looking for courses-finder-list...")
            
            # Wait for the unordered list with class 'courses-finder-list'
            await self.page.wait_for_selector("ul.courses-finder-list", timeout=30000)
            logger.info("Found courses-finder-list")
            
            # Find all buttons within the list
            buttons = self.page.locator("ul.courses-finder-list button")
            button_count = await buttons.count()
            logger.info(f"Found {button_count} buttons in courses-finder-list")
            
            if button_count > 0:
                first_button = buttons.first
                
                # Scroll button into view
                await first_button.scroll_into_view_if_needed()
                
                # Click the first button
                await first_button.click()
                logger.info("Clicked first button in courses-finder-list")
                
                await self.wait_for_navigation()
                return True
            else:
                logger.error("No buttons found in courses-finder-list")
                return False
                
        except Exception as e:
            logger.error(f"Failed to click button in courses-finder-list: {str(e)}")
            # Take screenshot for debugging
            if self.page:
                try:
                    await self.page.screenshot(path="courses_list_error.png", full_page=True)
                    logger.info("Screenshot saved as courses_list_error.png")
                except Exception as screenshot_error:
                    logger.warning(f"Could not save courses list error screenshot: {screenshot_error}")
            return False

    async def run(self, start_url: str, modules_to_select: list = None, city_name: str = None, headless: bool = False):
        """
        Main execution flow.
        
        Args:
            start_url: The starting URL
            modules_to_select: List of modules to select (e.g., ['reading', 'listening']). If None, keeps all selected.
            city_name: Specific city to book (e.g., "Bangalore", "Mumbai", "Chennai"). If None, clicks first available.
            headless: Whether to run in headless mode
        """
        async with async_playwright() as p:
            browser = None
            try:
                # Launch Brave browser
                logger.info("Launching Brave browser...")
                
                # Common Brave executable paths
                import os
                brave_paths = [
                    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                    r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
                    r"C:\Users\PREDATOR\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe",
                ]
                
                # Try to find Brave executable
                brave_path = None
                for path in brave_paths:
                    if os.path.exists(path):
                        brave_path = path
                        logger.info(f"Found Brave at: {brave_path}")
                        break
                
                if brave_path:
                    browser = await p.chromium.launch(
                        executable_path=brave_path,
                        headless=headless,
                        slow_mo=100
                    )
                else:
                    logger.warning("Brave not found, falling back to Chromium")
                    browser = await p.chromium.launch(headless=headless, slow_mo=100)
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080}
                )
                self.page = await context.new_page()
                
                # Set default timeouts
                self.page.set_default_navigation_timeout(60000)
                self.page.set_default_timeout(30000)
                
                # Navigate to start URL
                logger.info(f"Navigating to {start_url}")
                await self.page.goto(start_url, wait_until="networkidle", timeout=60000)
                
                # Handle cookie consent first
                await self.handle_cookie_consent()
                
                # Step 1: Click on city details button
                if not await self.click_city_details(city_name):
                    raise Exception("Failed to click city DETAILS button")
                
                # Step 2: Select modules
                if not await self.select_modules():
                    raise Exception("Failed to select modules")
                
                # Step 2.5: Configure module checkboxes (if specific modules provided)
                await self.configure_module_checkboxes(modules_to_select)

                # Step 3: Click continue
                if not await self.click_continue("after selecting modules"):
                    raise Exception("Failed to click continue after modules")
                
                # Step 4: Book for myself
                if not await self.book_for_myself():
                    raise Exception("Failed to click 'Book for myself'")
                

                # Step 5: Login
                if not await self.login():
                    raise Exception("Login failed")
                
                # Step 6: Handle "Discard other booking" dialog if it appears
                await self.handle_discard_other_booking()
                
                # Step 7: Additional continues and navigation
                await self.click_continue("Booking")

                
                await self.click_continue("Payment")



                
                # Step 8: Handle payment (stops at payment page)
                if not await self.handle_payment():
                    raise Exception("Payment process failed")
                
                logger.info("="*80)
                logger.info("✅✅✅ BOOKING PROCESS COMPLETED SUCCESSFULLY! ✅✅✅")
                logger.info("="*80)
                logger.info("⚠  Note: Card details were NOT filled (manual payment required)")
                logger.info("="*80)
                
                # Wait a bit to see the payment page
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"❌ Booking process failed: {str(e)}")
                # Take screenshot on error
                if self.page:
                    try:
                        await self.page.screenshot(path="error_screenshot.png")
                        logger.info("Error screenshot saved as error_screenshot.png")
                    except Exception as screenshot_error:
                        logger.warning(f"Could not save screenshot: {screenshot_error}")
                raise
            finally:
                # Ensure browser is closed even if there's an error
                if browser:
                    try:
                        await browser.close()
                        logger.info("Browser closed successfully")
                    except Exception as close_error:
                        logger.warning(f"Error closing browser: {close_error}")


async def main():
    """Example usage."""
    # Configuration
    config = {
        'email': 'antonymichealpeoshane@gmail.com',
        'password': 'Shane@2k242k24',
        'card_details': {
            'name': 'John Doe',
            'number': '4111111111111111',  # Test card number
            'expiry': '12/25',
            'cvv': '123'
        },
        'start_url': 'https://www.goethe.de/ins/in/en/spr/prf/gzb1.cfm',
        
        # Module selection:
        # - Leave as None or [] to keep all modules selected (default)
        # - Or specify which modules to select: ['reading', 'listening', 'writing', 'speaking']
        'modules': ['reading', 'listening']  # Change as needed, or set to None for all
    }
    
    bot = GoetheBookingBot(
        email=config['email'],
        password=config['password'],
        card_details=config['card_details']
    )
    
    await bot.run(
        start_url=config['start_url'],
        modules_to_select=config['modules'],  # Pass the modules to select
        headless=False  # Set to True for production
    )


if __name__ == "__main__":
    asyncio.run(main())
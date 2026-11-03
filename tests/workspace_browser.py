# Browser acceptance checks; base_url targets an isolated fixture server and artifacts holds review screenshots.
from pathlib import Path
import os
import sys

from playwright.sync_api import sync_playwright, expect

base_url = sys.argv[1]
artifacts = Path(os.environ.get('JAGENT_BROWSER_ARTIFACTS', '/tmp/jagent-milestone-a-review/browser'))
artifacts.mkdir(parents=True, exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    asset_failures = []
    page.on('response', lambda response: asset_failures.append(f'{response.status} {response.url}')
            if '/static/' in response.url and response.status >= 400 else None)
    console_errors = []
    page.on('console', lambda message: console_errors.append(message.text) if message.type == 'error' else None)

    def check_layout(width):
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}'
        links = page.locator('.sidebar nav a')
        boxes = [link.bounding_box() for link in links.all()]
        assert page.locator('.brand').evaluate("e => getComputedStyle(e).whiteSpace === 'nowrap' && e.scrollWidth <= e.clientWidth")
        for index, box in enumerate(boxes):
            assert box and box['height'] >= 44, f'Small navigation target at {width}'
            assert links.nth(index).evaluate("e => getComputedStyle(e).whiteSpace === 'nowrap' && e.scrollWidth <= e.clientWidth"), f'Clipped navigation at {width}'
            for other in boxes[index + 1:]:
                assert (box['x'] + box['width'] <= other['x'] + .5
                        or other['x'] + other['width'] <= box['x'] + .5
                        or box['y'] + box['height'] <= other['y'] + .5
                        or other['y'] + other['height'] <= box['y'] + .5), f'Navigation overlap at {width}'
        assert page.locator('body').evaluate('e => parseFloat(getComputedStyle(e).fontSize) >= 16')

    page.goto(base_url)
    expect(page.locator('.index-row')).to_have_count(3)
    expect(page.locator('#index-4')).to_have_count(0)
    expect(page.locator('#health-banner')).to_contain_text('Latest daily pipeline: degraded')
    expect(page.locator('.opportunity-detail:visible')).to_have_count(1)
    expect(page.locator('#index-1')).to_have_attribute('aria-current', 'true')
    page.locator('#index-1').focus()
    page.keyboard.press('ArrowDown')
    expect(page.locator('#index-2')).to_have_attribute('aria-current', 'true')
    page.keyboard.press('Enter')
    expect(page.locator('#posting-2')).to_be_focused()
    page.locator('#index-1').click()
    page.locator('#posting-1 .evidence-section').first.locator('summary').click()
    expect(page.locator('#posting-1 blockquote')).to_have_text('Python')
    page.screenshot(path=str(artifacts / 'opportunities-desktop.png'), full_page=True)
    page.keyboard.press('/')
    expect(page.locator('#q')).to_be_focused()
    page.locator('#q').fill('no-such-role')
    page.get_by_role('button', name='Search', exact=True).click()
    expect(page.get_by_role('heading', name='No roles match these filters.')).to_be_visible()
    page.goto(base_url)
    page.locator('input[name="saved"]').check()
    page.get_by_role('button', name='Search', exact=True).click()
    expect(page.locator('.index-row')).to_have_count(0)
    page.goto(base_url)
    page.get_by_text('Advanced filters', exact=True).click()
    page.locator('#seniority').select_option('mid')
    page.get_by_role('button', name='Apply filters').click()
    expect(page.locator('.index-row')).to_have_count(1)
    page.goto(base_url)
    # Historical saved roles remain reviewable even when excluded from the active index.
    response = page.request.post(base_url + '/reviews/4', form={'action': 'later', 'note': 'Archived context'})
    assert response.ok
    page.goto(base_url + '/?saved=1')
    expect(page.locator('.index-row')).to_have_count(1)
    page.locator('#index-4').click()
    expect(page.locator('#posting-4')).to_contain_text('recorded deadline has passed')
    expect(page.locator('#posting-4')).to_contain_text('availability on the original site is not verified')
    expect(page.locator('#note-4')).to_have_value('Archived context')
    page.screenshot(path=str(artifacts / 'saved-inactive-desktop.png'), full_page=True)
    page.locator('#reason-4').select_option('other')
    page.get_by_role('button', name='Skip', exact=True).click()
    expect(page.locator('#index-4')).to_have_count(0)
    page.goto(base_url)
    print('PASS: inactive Saved history stays accessible and reviewable while the active index excludes it')
    for width in (1440, 1024, 768, 390, 320):
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto(base_url)
        check_layout(width)
        row_boxes = [row.bounding_box() for row in page.locator('.index-row').all()]
        for first, second in zip(row_boxes, row_boxes[1:]):
            assert first['height'] >= 80 and second['y'] >= first['y'] + first['height'] - .5, f'Rows merge at {width}'
        assert page.locator('.index-row').first.evaluate("e => getComputedStyle(e).display === 'block' && getComputedStyle(e).textDecorationLine === 'none'")
        assert page.locator('.index-location').first.evaluate('e => parseFloat(getComputedStyle(e).fontSize) >= 13')
        page.screenshot(path=str(artifacts / f'opportunities-index-{width}.png'), full_page=True)
        title = page.locator('#index-2 .index-title').inner_text()
        page.locator('#index-2').click()
        expect(page.locator('#posting-2')).to_be_visible()
        expect(page.locator('#posting-2 h2')).to_have_text(title)
        expect(page.locator('#index-2')).to_have_attribute('aria-current', 'true')
        check_layout(width)
        if width <= 900:
            expect(page.locator('.opportunity-index')).not_to_be_visible()
        else:
            expect(page.locator('.opportunity-index')).to_be_visible()
            left = page.locator('.opportunity-index').bounding_box()
            right = page.locator('.intelligence-panel').bounding_box()
            assert right['x'] >= left['x'] + left['width'] - .5 and right['width'] >= 500
        expect(page.locator('#posting-2 .fit-summary')).to_be_visible()
        expect(page.locator('#posting-2 .links a').first).to_be_visible()
        expect(page.locator('#posting-2 .brief-save')).to_be_visible()
        page.screenshot(path=str(artifacts / f'opportunities-selected-{width}.png'), full_page=True)
        for action in ('later', 'skip', 'apply'):
            control = page.locator(f'#review-2 button[value="{action}"]')
            control.scroll_into_view_if_needed()
            expect(control).to_be_in_viewport()
        page.screenshot(path=str(artifacts / f'opportunities-decisions-{width}.png'))
        if width <= 900:
            page.get_by_role('button', name='← Opportunity index').click()
            expect(page.locator('#index-2')).to_be_focused()
            expect(page.locator('.opportunity-index')).to_be_visible()
        print(f'PASS {width}px: distinct rows, correct brief, panel mode, readable type, navigation geometry, controls, no overflow')
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.locator('#index-1').click()
    page.locator('#note-1').fill('Check the engineering team')
    assert not console_errors, console_errors
    page.route('**/reviews/1', lambda route: route.abort())
    page.get_by_role('button', name='Save for later', exact=True).click()
    expect(page.locator('#workspace-feedback')).to_contain_text('Could not confirm')
    expect(page.locator('#note-1')).to_have_value('Check the engineering team')
    expect(page.get_by_role('button', name='Save for later', exact=True)).to_be_enabled()
    page.unroute('**/reviews/1')
    console_errors.clear()  # The deliberately aborted review produces an expected network error.
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('#workspace-feedback')).to_contain_text('Saved for later')
    expect(page.locator('#index-1')).to_have_attribute('aria-current', 'true')
    expect(page.locator('#posting-1 .saved-badge')).to_be_visible()
    expect(page.locator('#note-1')).to_have_value('Check the engineering team')
    page.reload()
    page.locator('#index-1').click()
    expect(page.locator('#note-1')).to_have_value('Check the engineering team')
    page.locator('#index-3').click()
    page.get_by_role('button', name='Skip', exact=True).click()
    expect(page.locator('#reason-3')).to_be_focused()
    expect(page.locator('#posting-3')).to_be_visible()
    page.locator('#reason-3').select_option('salary')
    page.get_by_role('button', name='Skip', exact=True).click()
    expect(page.locator('#index-3')).to_have_count(0)
    page.locator('#index-2').click()
    page.locator('#note-2').fill('Prepare CV')
    page.get_by_role('button', name='Mark as applied ↗').click()
    expect(page.locator('#workspace-feedback')).to_contain_text('Application recorded')
    expect(page.locator('#index-2')).to_have_count(0)
    page.goto(base_url + '/applied')
    page.locator('.application-item > summary').click()
    expect(page.locator('.application-note')).to_have_text('Prepare CV')
    for route in ('/applied', '/profile', '/filters', '/health'):
        page.goto(base_url + route)
        if route == '/health':
            expect(page.get_by_role('region', name='Latest pipeline outcome')).to_contain_text('One source timed out')
        for width in (1440, 1024, 768, 390, 320):
            page.set_viewport_size({'width': width, 'height': 900})
            check_layout(width)
            page.screenshot(path=str(artifacts / f'{route.strip("/")}-{width}.png'), full_page=True)
    page.goto(base_url + '/profile')
    expect(page.locator('#profile_text')).to_be_in_viewport()
    profile_help = page.locator('.form-help')
    expect(profile_help).not_to_have_attribute('open', '')
    profile_help.locator('summary').click()
    expect(profile_help).to_contain_text('configured AI service')
    profile_help.locator('summary').click()
    original_profile = page.locator('#profile_text').input_value()
    page.locator('#profile_text').fill('')
    page.get_by_role('button', name='Save profile', exact=True).click()
    expect(page.locator('#profile_text')).to_be_focused()
    page.locator('#profile_text').fill(original_profile)
    page.get_by_role('button', name='Save profile', exact=True).click()
    expect(page.get_by_role('status').filter(has_text='Your profile is saved.')).to_be_visible()
    page.goto(base_url + '/filters')
    expect(page.locator('#countries')).to_be_in_viewport()
    expect(page.locator('.filter-form legend')).to_have_text(['Locations & remote', 'Roles & exclusions', 'Local discovery'])
    page.locator('.form-help summary').click()
    expect(page.locator('.form-help')).to_contain_text('does not predict a hiring outcome')
    page.get_by_role('button', name='Save preferences and update queue').click()
    expect(page).to_have_url(base_url + '/')
    assert not errors, errors
    assert not console_errors, console_errors
    assert not asset_failures, asset_failures
    fallback = browser.new_page(java_script_enabled=False, viewport={'width': 390, 'height': 900})
    fallback.goto(base_url)
    expect(fallback.locator('#posting-1')).to_be_visible()
    fallback.locator('#note-1').fill('Saved without JavaScript')
    fallback.get_by_role('button', name='Update saved role').click()
    expect(fallback.locator('#note-1')).to_have_value('Saved without JavaScript')
    fallback.screenshot(path=str(artifacts / 'no-javascript-390.png'), full_page=True)
    fallback.goto(base_url + '/profile')
    fallback.locator('.form-help summary').click()
    expect(fallback.locator('.form-help')).to_contain_text('configured AI service')
    blocked = browser.new_page(viewport={'width': 768, 'height': 900})
    blocked.route('**/static/workspace.js*', lambda route: route.abort())
    blocked.goto(base_url)
    expect(blocked.locator('.opportunity-workspace.enhanced')).to_have_count(0)
    blocked.locator('#index-1').click()
    expect(blocked.locator('#posting-1')).to_be_in_viewport()
    expect(blocked.locator('#note-1')).to_have_value('Saved without JavaScript')
    blocked.locator('#note-1').fill('Saved after script failure')
    blocked.get_by_role('button', name='Update saved role').click()
    expect(blocked.locator('#note-1')).to_have_value('Saved after script failure')
    print('PASS: JavaScript disabled and script blocked; anchor detail navigation and persisted Save work')
    browser.close()
print('PASS: selection, keyboard, search, filters, responsive layouts (320–1440px), error recovery, Save/Skip/Apply persistence, profile save, preferences save, no-JavaScript fallback; no browser errors.')
print(f'Screenshots: {artifacts}')

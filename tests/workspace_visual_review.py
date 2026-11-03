# Inspect live pages without writes; base_url targets the running app and artifacts stores screenshots for human review.
from pathlib import Path
import json
import sys

from playwright.sync_api import expect, sync_playwright

base_url = sys.argv[1].rstrip('/')
artifacts = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('/tmp/jagent-ui-refinement/after')
measurements = []
artifacts.mkdir(parents=True, exist_ok=True)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.on('response', lambda response: errors.append(f'{response.status} {response.url}')
            if response.status >= 400 else None)
    for width in (390, 768, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 1000})
        for route in ('', 'applied', 'profile', 'filters', 'health'):
            page.goto(base_url + '/' + route)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (route, width)
            navigation = page.locator('.sidebar nav a')
            boxes = [link.bounding_box() for link in navigation.all()]
            for index, box in enumerate(boxes):
                assert box['width'] > 0 and box['height'] >= 44, (route, width, box)
                assert navigation.nth(index).evaluate("e => getComputedStyle(e).whiteSpace === 'nowrap' && e.scrollWidth <= e.clientWidth")
                for other in boxes[index + 1:]:
                    assert (box['x'] + box['width'] <= other['x'] + .5
                            or other['x'] + other['width'] <= box['x'] + .5
                            or box['y'] + box['height'] <= other['y'] + .5
                            or other['y'] + other['height'] <= box['y'] + .5), (width, boxes)
            if not route:
                rows = page.locator('.index-row')
                bounds = [row.bounding_box() for row in rows.all()]
                assert len(bounds) >= 2
                workspace = page.locator('.opportunity-workspace').bounding_box()
                list_box = page.locator('.index-rows').bounding_box()
                visible_bottom = min(1000, list_box['y'] + list_box['height'])
                visible_rows = sum(box['y'] >= list_box['y'] and box['y'] + box['height'] <= visible_bottom for box in bounds)
                measurements.append({'page': 'opportunities', 'width': width, 'workspace_top': round(workspace['y']),
                                     'first_row_height': round(bounds[0]['height']), 'fully_visible_rows': visible_rows})
                for first, second in zip(bounds, bounds[1:]):
                    assert first['height'] >= 80 and second['y'] >= first['y'] + first['height'] - .5
                page.screenshot(path=str(artifacts / f'opportunities-index-{width}.png'))
                title = rows.nth(1).locator('.index-title').inner_text()
                company = rows.nth(1).locator('.index-company').inner_text()
                posting_id = rows.nth(1).get_attribute('data-posting')
                rows.nth(1).click()
                detail = page.locator('.opportunity-detail:visible')
                expect(detail).to_have_attribute('id', f'posting-{posting_id}')
                expect(detail.locator('h2').first).to_have_text(title)
                expect(detail.locator('.company')).to_contain_text(company)
                expect(page.locator('.intelligence-panel')).to_be_visible()
                if width > 900:
                    left = page.locator('.opportunity-index').bounding_box()
                    right = page.locator('.intelligence-panel').bounding_box()
                    assert right['x'] >= left['x'] + left['width'] - .5 and right['width'] >= 500
                    assert page.locator('.index-rows').evaluate('e => e.scrollHeight > e.clientHeight')
                else:
                    expect(page.locator('.opportunity-index')).not_to_be_visible()
                page.screenshot(path=str(artifacts / f'opportunities-selected-{width}.png'), full_page=True)
                detail.locator('.evidence-section summary').first.click()
                detail.locator('.review-form').scroll_into_view_if_needed()
                page.screenshot(path=str(artifacts / f'opportunities-decisions-{width}.png'))
                print(f'PASS live opportunities {width}px: no overflow; navigation single-line, separate, 44px targets; distinct rows; correct selection; intentional panel mode')
            else:
                if route in ('profile', 'filters'):
                    editor = page.locator('#profile_text' if route == 'profile' else '#countries').bounding_box()
                    measurements.append({'page': route, 'width': width, 'first_control_top': round(editor['y'])})
                page.screenshot(path=str(artifacts / f'{route}-viewport-{width}.png'))
                page.screenshot(path=str(artifacts / f'{route}-{width}.png'), full_page=True)
                if route == 'applied':
                    page.locator('.application-item > summary').first.click()
                    page.screenshot(path=str(artifacts / f'applied-expanded-{width}.png'), full_page=True)
                print(f'PASS live {route} {width}px: no overflow; navigation single-line, separate, 44px targets')
    assert not errors, errors
    print('PASS live: no console errors, uncaught errors or failed HTTP responses')
    browser.close()
(artifacts / 'measurements.json').write_text(json.dumps(measurements, indent=2) + '\n')

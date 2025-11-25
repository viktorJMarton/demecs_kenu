"""Admin content blueprint - allows editing of hero, FAQ and other sections."""

from __future__ import annotations

import json

from flask import Blueprint, render_template, request, redirect, url_for, flash
import os
from werkzeug.utils import secure_filename
from flask import current_app

from ..auth import login_required
from ..services import content_service

bp = Blueprint('admin_content', __name__, url_prefix='/admin/content')


@bp.route('/', methods=['GET'])
@login_required
def sections():
    """Render the admin content management page."""
    sections = content_service.list_sections()
    sections_map = {section['slug']: section for section in sections}
    generic_sections = [section for section in sections if section['slug'] not in ('hero', 'faq')]
    return render_template(
        'admin/content.html',
        sections=sections,
        section_map=sections_map,
        generic_sections=generic_sections
    )


@bp.route('/<slug>', methods=['POST'])
@login_required
def update_section(slug: str):
    """Persist updates for a single page section."""
    section = content_service.get_section(slug)
    default_label = section.get('label', slug.replace('_', ' ').title())
    label = (request.form.get('label') or default_label).strip()
    if not label:
        label = default_label

    if slug == 'hero':
        content = {
            'headline': request.form.get('headline', '').strip(),
            'subheadline': request.form.get('subheadline', '').strip(),
            'video_url': request.form.get('video_url', '').strip() or '/static/hero-bg.mp4'
        }
        if not content['headline']:
            flash('A főcím megadása kötelező.', 'error')
            return redirect(url_for('admin_content.sections'))
    elif slug == 'faq':
        questions = request.form.getlist('question[]')
        answers = request.form.getlist('answer[]')
        items = []
        for idx, question in enumerate(questions):
            q_value = (question or '').strip()
            a_value = (answers[idx] if idx < len(answers) else '').strip()
            if not q_value and not a_value:
                continue
            items.append({'question': q_value, 'answer': a_value})
        if not items:
            flash('Legalább egy kérdés-válasz pár szükséges a GYIK szekcióhoz.', 'error')
            return redirect(url_for('admin_content.sections'))

        tips_raw = request.form.getlist('faq_tip[]')
        tips = [tip.strip() for tip in tips_raw if (tip or '').strip()]
        content = {'items': items, 'tips': tips}
    elif slug == 'info_cards':
        heading = request.form.get('heading', '').strip()
        if not heading:
            heading = 'Általános leírás a vállalkozásról'

        card_titles = request.form.getlist('card_title[]')
        card_descriptions = request.form.getlist('card_description[]')
        cards = []
        for idx, title in enumerate(card_titles):
            clean_title = (title or '').strip()
            clean_desc = (card_descriptions[idx] if idx < len(card_descriptions) else '').strip()
            if not clean_title and not clean_desc:
                continue
            cards.append({
                'title': clean_title or f'Kártya #{idx + 1}',
                'description': clean_desc
            })
        if not cards:
            flash('Legalább egy kártyát adj meg.', 'error')
            return redirect(url_for('admin_content.sections'))

        highlight_icons = request.form.getlist('highlight_icon[]')
        highlight_labels = request.form.getlist('highlight_label[]')
        highlights = []
        for idx, icon in enumerate(highlight_icons):
            clean_icon = (icon or '').strip()
            clean_label = (highlight_labels[idx] if idx < len(highlight_labels) else '').strip()
            if not clean_icon and not clean_label:
                continue
            highlights.append({
                'icon': clean_icon or '🖼️',
                'label': clean_label or f'Ikon #{idx + 1}'
            })

        content = {
            'heading': heading,
            'cards': cards,
            'highlights': highlights
        }
        # Handle uploaded images for cards and highlights (optional)
        try:
            # determine uploads root (default to project public/uploads)
            uploads_root = current_app.config.get('UPLOADS_ROOT')
            if not uploads_root:
                uploads_root = os.path.abspath(os.path.join(current_app.root_path, '..', 'public', 'uploads'))
            os.makedirs(uploads_root, exist_ok=True)

            # target subfolder for info cards
            target_dir = os.path.join(uploads_root, 'content', 'info_cards')
            os.makedirs(target_dir, exist_ok=True)

            card_files = request.files.getlist('card_image[]') or []
            existing_card_images = request.form.getlist('existing_card_image[]') or []

            for idx, card in enumerate(content['cards']):
                file_obj = card_files[idx] if idx < len(card_files) else None
                existing = existing_card_images[idx] if idx < len(existing_card_images) else ''
                if file_obj and getattr(file_obj, 'filename', None):
                    filename = secure_filename(file_obj.filename)
                    # ensure unique name
                    base, ext = os.path.splitext(filename)
                    filename = f"{base}_{int(__import__('time').time())}{ext}"
                    save_path = os.path.join(target_dir, filename)
                    file_obj.save(save_path)
                    # store relative path under uploads folder
                    card['image'] = os.path.join('content', 'info_cards', filename).replace('\\', '/')
                elif existing:
                    card['image'] = existing

            highlight_files = request.files.getlist('highlight_image[]') or []
            existing_highlight_images = request.form.getlist('existing_highlight_image[]') or []
            # capture original highlights to detect removals
            original_highlights = section.get('content', {}).get('highlights', []) if section else []
            for idx, h in enumerate(content['highlights']):
                file_obj = highlight_files[idx] if idx < len(highlight_files) else None
                existing = existing_highlight_images[idx] if idx < len(existing_highlight_images) else ''
                if file_obj and getattr(file_obj, 'filename', None):
                    filename = secure_filename(file_obj.filename)
                    base, ext = os.path.splitext(filename)
                    filename = f"{base}_{int(__import__('time').time())}{ext}"
                    save_path = os.path.join(target_dir, filename)
                    file_obj.save(save_path)
                    h['image'] = os.path.join('content', 'info_cards', filename).replace('\\', '/')
                elif existing:
                    h['image'] = existing
                else:
                    # no existing value: admin cleared the image — remove original file if present
                    try:
                        orig_img = None
                        if idx < len(original_highlights):
                            orig_img = original_highlights[idx].get('image')
                        if orig_img:
                            abs_path = os.path.normpath(os.path.join(uploads_root, orig_img))
                            # ensure deletion only inside uploads_root
                            if abs_path.startswith(os.path.normpath(uploads_root)) and os.path.exists(abs_path):
                                os.remove(abs_path)
                    except Exception:
                        # swallow errors — deletion is best-effort
                        pass
        except Exception:
            # avoid breaking content save if uploads fail; log is not available here
            pass
    elif slug == 'contact_socials':
        facebook_url = (request.form.get('facebook_url') or '').strip()
        instagram_url = (request.form.get('instagram_url') or '').strip()
        tiktok_url = (request.form.get('tiktok_url') or '').strip()
        content = {
            'facebook_url': facebook_url,
            'instagram_url': instagram_url,
            'tiktok_url': tiktok_url,
        }
    elif slug in ('terms_page', 'privacy_page'):
        title = (request.form.get('title') or '').strip()
        effective_date = (request.form.get('effective_date') or '').strip()
        body = (request.form.get('body') or '').strip()
        if not body:
            flash('A jogi oldal tartalma nem lehet üres.', 'error')
            return redirect(url_for('admin_content.sections'))
        if not title:
            title = section.get('content', {}).get('title') or default_label
        content = {
            'title': title,
            'effective_date': effective_date,
            'body': body,
        }
        label = section.get('label', label)
    else:
        raw_json = request.form.get('content_json', '').strip()
        if not raw_json:
            flash('A tartalom mező nem lehet üres.', 'error')
            return redirect(url_for('admin_content.sections'))
        try:
            content = json.loads(raw_json)
        except json.JSONDecodeError:
            flash('Érvénytelen JSON formátum.', 'error')
            return redirect(url_for('admin_content.sections'))

    content_service.update_section(slug, label, content)
    flash(f'{label} szekció frissítve.', 'success')
    return redirect(url_for('admin_content.sections'))

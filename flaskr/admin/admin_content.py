"""Admin content blueprint - allows editing of hero, FAQ and other sections."""

from __future__ import annotations

import json

from flask import Blueprint, render_template, request, redirect, url_for, flash

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
        content = {'items': items}
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

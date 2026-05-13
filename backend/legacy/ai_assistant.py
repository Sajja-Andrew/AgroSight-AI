"""
Smart Crop AI Assistant - Open Source Mind
A transparent, rule-based intelligence engine that captures user context,
detects intent, filters relevant disease information, and generates feedback.
"""

import random
import re
from difflib import get_close_matches


class AIAssistant:
    """
    Domain-specific assistant for crop disease detection.
    Uses keyword-based intent detection and structured data retrieval
    instead of opaque LLM black-boxes — the "open source mind".
    """

    def __init__(self, disease_db):
        self.disease_db = disease_db
        self.intents = {
            'disease_info': [
                'what is', 'tell me about', 'symptoms of', 'info on',
                'information', 'describe', 'explain', 'blight', 'rust',
                'mold', 'virus', 'mite', 'healthy', 'late blight',
                'early blight', 'leaf spot', 'gray leaf', 'northern leaf',
                'cercospora', 'bacterial', 'mosaic', 'yellow leaf curl',
                'target spot', 'septoria', 'spider mite', 'common rust'
            ],
            'detection_history': [
                'history', 'past detections', 'my detections', 'what have i detected',
                'previous scans', 'records', 'scanned', 'found so far', 'all my',
                'what diseases have', 'my results'
            ],
            'prevention_advice': [
                'prevent', 'prevention', 'avoid', 'stop disease',
                'how to protect', 'how to prevent', 'keep away', 'protect from',
                'what should i do to avoid', 'keep my crops safe'
            ],
            'last_detection': [
                'last detection', 'latest result', 'recent scan', 'last disease',
                'what did i scan', 'most recent', 'last time', 'previous result',
                'my last', 'the result i just got'
            ],
            'trend_analysis': [
                'trend', 'analysis', 'how am i doing', 'statistics', 'patterns',
                'overview', 'summary', 'performance', 'getting better', 'getting worse',
                'my stats', 'how are my crops'
            ],
            'feedback_help': [
                'feedback', 'report wrong', 'incorrect', 'wrong prediction',
                'fix result', 'report error', 'correction', 'retrain',
                'this is not right', 'wrong disease'
            ],
            'compare_diseases': [
                'compare', 'difference between', ' vs ', 'which is worse',
                'versus', 'better or worse', 'more severe', 'which one',
                'difference', 'similarities between'
            ],
            'crop_diseases': [
                'what diseases affect', 'diseases of', 'problems with',
                'crop diseases', 'affect tomato', 'affect corn', 'affect potato',
                'tomato diseases', 'corn diseases', 'potato diseases',
                'maize diseases', 'what can happen to my'
            ],
            'treatment_plan': [
                'treat', 'treatment', 'cure', 'fix', 'what should i do',
                'how do i fix', 'how to treat', 'solution for', 'remedy',
                'what medicine', 'what fungicide', 'how to cure', 'what to apply',
                'how do i', 'what can i do', 'what do i do', 'what steps',
                'how should i', 'recommended treatment', 'best treatment',
                'how to manage', 'how to control'
            ],
            'identify_from_symptoms': [
                'brown spots', 'yellow leaves', 'wilting', 'spots on',
                'lesions', 'mold on', 'white patches', 'red spots',
                'leaf curling', 'curling', 'yellowing', 'dying leaves',
                'discolored', 'rotting', 'stunted', 'dropping',
                'what disease has', 'what causes', 'why are my', 'symptoms',
                'my leaves', 'my plant', 'my tomato', 'my corn', 'my potato'
            ],
            'severity_check': [
                'how severe', 'severity of', 'is it serious', 'how bad',
                'dangerous', 'worried about', 'should i be concerned',
                'is this bad', 'how critical'
            ],
            'weather_advice': [
                'rain', 'humidity', 'weather', 'wet', 'dry', 'hot', 'cold',
                'climate', 'season', 'monsoon', 'drought', 'after rain'
            ],
            'greeting': [
                'hello', 'hi ', 'hey ', 'good morning', 'good afternoon',
                'good evening', 'howdy', 'greetings', 'what\'s up'
            ],
            'farewell': [
                'bye', 'goodbye', 'see you', 'thank', 'thanks', 'appreciate',
                'that\'s all', 'done', 'helpful'
            ],
            'general_help': [
                'help', 'what can you do', 'capabilities', 'assist', 'support',
                'who are you', 'what are you', 'your name', 'how do you work'
            ]
        }
        self.severity_rank = {'High': 3, 'Medium': 2, 'Low': 1, 'None': 0, 'Unknown': -1}
        self.crop_keywords = {
            'tomato': ['Tomato'],
            'potato': ['Potato'],
            'corn': ['Corn_(maize)'],
            'maize': ['Corn_(maize)']
        }

    def process(self, message, user_history=None, last_detection=None):
        """
        Main entry point.
        Returns dict: {intent, response, reasoning}
        """
        intent = self._detect_intent(message)
        reasoning = self._think(intent, message, user_history, last_detection)
        response = self._generate_response(
            intent, message, user_history or [], last_detection
        )
        return {'intent': intent, 'response': response, 'reasoning': reasoning}

    def _think(self, intent, message, user_history, last_detection):
        """Show reasoning steps — the 'open source mind' transparency."""
        thoughts = []
        thoughts.append(f"1. Detected intent: '{intent}'")

        if user_history:
            thoughts.append(f"2. User has {len(user_history)} past detections")
        else:
            thoughts.append("2. No user history available")

        if last_detection:
            thoughts.append(f"3. Last detection: {last_detection.get('disease', 'unknown')} ({last_detection.get('confidence', 0)}%)")
        else:
            thoughts.append("3. No recent detection context")

        disease = self._find_disease(message)
        if disease:
            thoughts.append(f"4. Matched disease in database: {self.disease_db.get(disease, {}).get('name', disease)}")
        else:
            thoughts.append("4. No direct disease match from message text")

        return '\n'.join(thoughts)

    def _detect_intent(self, message):
        """Score keywords to find best intent."""
        text = re.sub(r'[^\w\s]', ' ', message.lower())
        scores = {}
        for intent_name, keywords in self.intents.items():
            score = sum(1 for kw in keywords if kw in text)
            scores[intent_name] = score
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else 'general_help'

    def _find_disease(self, text):
        """Fuzzy match user text against disease database keys and display names."""
        text_lc = text.lower()
        text_words = set(text_lc.split())

        # Check each disease for strong name component matches
        best_match = None
        best_score = 0

        for key, val in self.disease_db.items():
            vname = val.get('name', '').lower()

            # Exact display name match
            if vname in text_lc:
                return key

            # Split display name by common separators to get components
            components = [c.strip() for c in re.split(r'[/\-\(\)]', vname) if c.strip()]
            for comp in components:
                if len(comp) > 5 and comp in text_lc:
                    return key

            # Score by word overlap
            disease_words = set(w for w in re.split(r'[\s/\-\(\),]', vname) if len(w) > 3)
            overlap = disease_words & text_words
            score = len(overlap)
            # Boost for longer component matches
            for w in overlap:
                if len(w) > 6:
                    score += 1
            if score > best_score:
                best_score = score
                best_match = key

        if best_score >= 2:
            return best_match

        return None

    def _find_crop(self, text):
        """Identify which crop the user is asking about."""
        text_lc = text.lower()
        for crop, prefixes in self.crop_keywords.items():
            if crop in text_lc:
                return prefixes
        return None

    def _match_symptoms(self, text):
        """Try to match described symptoms to diseases."""
        text_lc = text.lower()
        symptom_keywords = {
            'brown spots': ['Early_blight', 'Bacterial_spot', 'Septoria'],
            'yellow leaves': ['Yellow_Leaf_Curl_Virus', 'mosaic'],
            'yellowing': ['Yellow_Leaf_Curl_Virus'],
            'water-soaked': ['Late_blight', 'Bacterial_spot'],
            'white mold': ['Late_blight', 'Leaf_Mold'],
            'mold': ['Leaf_Mold', 'Late_blight'],
            'gray': ['Gray_leaf_spot', 'Leaf_Mold'],
            'grayish': ['Gray_leaf_spot'],
            'rust': ['Common_rust_'],
            'reddish': ['Common_rust_'],
            'pustules': ['Common_rust_'],
            'concentric rings': ['Early_blight', 'Target_Spot'],
            'bull': ['Early_blight'],
            'curling': ['Yellow_Leaf_Curl_Virus', 'Spider_mites'],
            'wilting': ['Late_blight', 'Bacterial_spot'],
            'lesions': ['Late_blight', 'Northern_Leaf_Blight', 'Gray_leaf_spot'],
            'long lesions': ['Northern_Leaf_Blight'],
            'rectangular': ['Gray_leaf_spot'],
            'olive green': ['Leaf_Mold'],
            'spider': ['Spider_mites'],
            'tiny dots': ['Spider_mites'],
            'spots on fruit': ['Bacterial_spot', 'Target_Spot'],
            'dying': ['Late_blight', 'Early_blight'],
        }

        matched = set()
        for symptom, disease_hints in symptom_keywords.items():
            if symptom in text_lc:
                for hint in disease_hints:
                    for key in self.disease_db.keys():
                        if hint.lower() in key.lower():
                            matched.add(key)

        return list(matched)

    def _generate_response(self, intent, message, user_history, last_detection):
        # Greeting
        if intent == 'greeting':
            greetings = [
                "Hello! I'm your Smart Crop Assistant. I can help you identify diseases, review your detection history, suggest treatments, and answer any crop health questions. What can I do for you today?",
                "Hey there! Ready to help protect your crops. Ask me about diseases, upload an image for analysis, or check your past results.",
                "Good day! I'm here to assist with crop disease detection and advice. What would you like to explore?"
            ]
            return random.choice(greetings)

        # Farewell / Thanks
        if intent == 'farewell':
            return (
                "You're welcome! I'm always here if you need help with crop diseases, "
                "detection analysis, or prevention advice. Happy farming!"
            )

        # Disease info
        if intent == 'disease_info':
            disease = self._find_disease(message)
            if disease:
                d = self.disease_db[disease]
                return (
                    f"**{d['name']}** — Severity: {d['severity']}\n\n"
                    f"**Symptoms:** {d['symptoms']}\n\n"
                    f"**Solution:** {d['solution']}\n\n"
                    f"**Prevention:** {d['prevention']}\n\n"
                    f"Want to know how this compares to similar diseases, or how to prevent it?"
                )
            examples = ', '.join([v['name'] for v in list(self.disease_db.values())[:5]]) + '...'
            return (
                f"I can describe any disease in our database. Try naming one, e.g.: {examples}\n\n"
                f"Or describe the symptoms you're seeing (brown spots, yellow leaves, wilting, etc.) and I'll try to identify it."
            )

        # Detection history
        if intent == 'detection_history':
            if not user_history:
                return "You have no detection history yet. Upload a plant image to get started! Your scans will be saved here for future reference."
            counts = {}
            for h in user_history:
                counts[h.get('disease', 'Unknown')] = counts.get(h.get('disease', 'Unknown'), 0) + 1
            top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
            summary = '\n'.join([f"  • {k}: {v} time(s)" for k, v in top])
            healthy_count = counts.get('Healthy Corn (Maize)', 0) + counts.get('Healthy Potato', 0) + counts.get('Healthy Tomato', 0)
            concern_count = len(user_history) - healthy_count

            response = f"**Your Detection History ({len(user_history)} total)**\n\nTop findings:\n{summary}\n\n"
            if concern_count > 0:
                response += f"You have {concern_count} disease detection(s). Regular monitoring is key to early intervention."
            else:
                response += "All your detections show healthy plants. Great job keeping your crops healthy!"
            return response

        # Last detection
        if intent == 'last_detection':
            if not last_detection:
                return "I don't see a recent detection. Try scanning a plant image first, and I'll remember the result for follow-up questions."
            ld = last_detection
            response = (
                f"**Last Detection:** {ld.get('disease', 'Unknown')}\n"
                f"• Confidence: {ld.get('confidence', 0)}%\n"
                f"• Severity: {ld.get('severity', 'Unknown')}\n"
                f"• Date: {ld.get('date', 'Recently')[:10]}\n\n"
            )
            disease = self._find_disease(ld.get('disease', ''))
            if disease:
                d = self.disease_db[disease]
                response += f"**Quick Info:** {d['symptoms'][:120]}...\n\nAsk me for full details or treatment options."
            return response

        # Trend analysis
        if intent == 'trend_analysis':
            if not user_history or len(user_history) < 2:
                return "Not enough data for trends yet. Keep scanning your crops regularly and I'll build insights for you!"
            confs = [h['confidence'] for h in user_history if 'confidence' in h]
            avg = round(sum(confs) / len(confs), 1) if confs else 0
            sev = {}
            for h in user_history:
                sev[h.get('severity', 'Unknown')] = sev.get(h.get('severity', 'Unknown'), 0) + 1
            common = max(sev, key=sev.get)
            recent = user_history[:5]
            recent_concerns = [r for r in recent if 'healthy' not in r.get('disease', '').lower()]

            response = (
                f"**Trends from your {len(user_history)} detections:**\n\n"
                f"• Average confidence: {avg}%\n"
                f"• Most common severity: {common} ({sev[common]} cases)\n"
                f"• Recent concerns: {len(recent_concerns)} out of last 5 scans\n\n"
            )
            if recent_concerns:
                response += "It looks like you've been finding some issues. Consider reviewing prevention strategies for the most common findings."
            else:
                response += "Your recent scans look good. Keep up the regular monitoring!"
            return response

        # Prevention advice
        if intent == 'prevention_advice':
            disease = self._find_disease(message)
            if disease:
                d = self.disease_db[disease]
                return (
                    f"**Prevention for {d['name']}:**\n\n"
                    f"{d['prevention']}\n\n"
                    f"**Additional tips:**\n"
                    f"• Scout your fields weekly for early signs\n"
                    f"• Maintain proper plant spacing for airflow\n"
                    f"• Remove and destroy infected plant material promptly\n"
                    f"• Use certified disease-free seeds when possible"
                )
            return (
                "**General Prevention Tips:**\n\n"
                "• Use certified, disease-resistant seeds and varieties\n"
                "• Rotate crops annually to break disease cycles\n"
                "• Maintain proper plant spacing for good airflow\n"
                "• Avoid overhead irrigation when possible\n"
                "• Scout fields regularly and remove infected material\n"
                "• Keep tools clean to avoid spreading pathogens\n"
                "• Ensure balanced fertilization — healthy plants resist disease better\n\n"
                "Want prevention advice for a specific disease? Just name it!"
            )

        # Treatment plan
        if intent == 'treatment_plan':
            disease = self._find_disease(message)
            if disease:
                d = self.disease_db[disease]
                is_healthy = 'healthy' in d['name'].lower()
                if is_healthy:
                    return (
                        f"**{d['name']}** — Your plant appears healthy!\n\n"
                        f"**Maintenance:** {d['solution']}\n\n"
                        f"**Prevention:** {d['prevention']}"
                    )
                return (
                    f"**Treatment Plan for {d['name']}:**\n\n"
                    f"**Immediate action:** {d['solution']}\n\n"
                    f"**Prevention going forward:** {d['prevention']}\n\n"
                    f"**Severity:** {d['severity']}\n\n"
                    f"If this is your first detection, act quickly. {d['severity']} severity diseases can spread rapidly under favorable conditions."
                )
            return (
                "I can create a treatment plan if you tell me the disease name or describe the symptoms.\n\n"
                "For example:\n"
                "• 'How do I treat tomato late blight?'\n"
                "• 'My corn leaves have brown spots with yellow halos'\n\n"
                "Uploading an image for detection will also give you a targeted treatment plan."
            )

        # Identify from symptoms
        if intent == 'identify_from_symptoms':
            matches = self._match_symptoms(message)
            if matches:
                if len(matches) == 1:
                    d = self.disease_db[matches[0]]
                    return (
                        f"Based on your description, this sounds like **{d['name']}**.\n\n"
                        f"**Why I think so:** {d['symptoms']}\n\n"
                        f"**What to do:** {d['solution']}\n\n"
                        f"For the most accurate diagnosis, upload a clear image of the affected leaves."
                    )
                else:
                    response = "Your symptoms could match a few possibilities:\n\n"
                    for i, m in enumerate(matches[:3], 1):
                        d = self.disease_db[m]
                        response += f"{i}. **{d['name']}** ({d['severity']} severity)\n   Key sign: {d['symptoms'][:100]}...\n\n"
                    response += "Upload an image for precise identification, or tell me more details about the symptoms."
                    return response
            return (
                "I'd like to help identify the issue. Could you describe the symptoms more specifically?\n\n"
                "Helpful details:\n"
                "• Color of spots or lesions (brown, yellow, black, white)\n"
                "• Location on plant (leaves, stems, fruit)\n"
                "• Pattern (concentric rings, water-soaked, rectangular)\n"
                "• Crop type (tomato, corn, potato)\n"
                "• Weather conditions recently (rainy, humid, dry)\n\n"
                "Or simply upload a photo for AI detection!"
            )

        # Crop diseases
        if intent == 'crop_diseases':
            crop_prefixes = self._find_crop(message)
            if crop_prefixes:
                matched = []
                for key, val in self.disease_db.items():
                    if any(prefix in key for prefix in crop_prefixes):
                        matched.append(val)
                healthy = [m for m in matched if 'healthy' in m['name'].lower()]
                diseases = [m for m in matched if 'healthy' not in m['name'].lower()]
                response = f"**Diseases affecting {'/'.join([p.replace('_(maize)', '').replace('___', ' ') for p in crop_prefixes])}:**\n\n"
                for d in diseases:
                    response += f"• **{d['name']}** — {d['severity']} severity\n  {d['symptoms'][:80]}...\n\n"
                if healthy:
                    response += "(Plus healthy plant reference for comparison)\n\n"
                response += "Ask me about any specific disease for full details on symptoms, treatment, and prevention."
                return response
            return (
                "I can list diseases for specific crops. Try asking:\n"
                "• 'What diseases affect tomatoes?'\n"
                "• 'Corn disease problems'\n"
                "• 'Potato diseases'"
            )

        # Severity check
        if intent == 'severity_check':
            disease = self._find_disease(message)
            if disease:
                d = self.disease_db[disease]
                sev = d['severity']
                if sev == 'High':
                    return (
                        f"**{d['name']}** is rated **HIGH severity**.\n\n"
                        f"This disease can spread rapidly and cause significant yield loss. "
                        f"I recommend taking immediate action:\n"
                        f"• {d['solution']}\n\n"
                        f"Don't wait — high severity diseases worsen quickly under favorable conditions."
                    )
                elif sev == 'Medium':
                    return (
                        f"**{d['name']}** is rated **MEDIUM severity**.\n\n"
                        f"It's manageable with prompt treatment:\n"
                        f"• {d['solution']}\n\n"
                        f"Monitor regularly and act before conditions worsen."
                    )
                elif sev == 'Low':
                    return (
                        f"**{d['name']}** is rated **LOW severity**.\n\n"
                        f"Usually manageable with basic care:\n"
                        f"• {d['solution']}\n\n"
                        f"Keep monitoring but it's not immediately threatening."
                    )
                else:
                    return f"**{d['name']}** — Severity: {sev}. {d['solution']}"
            return "Which disease would you like me to assess? Just name it or describe the symptoms."

        # Compare diseases
        if intent == 'compare_diseases':
            found = []
            for key, val in self.disease_db.items():
                if val['name'].lower() in message.lower():
                    found.append(key)
                else:
                    # Check individual words
                    words = val['name'].lower().replace('/', ' ').replace('-', ' ').split()
                    if any(len(w) > 4 and w in message.lower() for w in words):
                        if key not in found:
                            found.append(key)
            # Deduplicate while preserving order
            seen = set()
            unique_found = []
            for f in found:
                if f not in seen:
                    seen.add(f)
                    unique_found.append(f)
            if len(unique_found) >= 2:
                a = self.disease_db[unique_found[0]]
                b = self.disease_db[unique_found[1]]
                worse = (
                    a['name']
                    if self.severity_rank.get(a['severity'], 0) >
                       self.severity_rank.get(b['severity'], 0)
                    else b['name']
                )
                return (
                    f"**Disease Comparison:**\n\n"
                    f"**{a['name']}**\n"
                    f"• Severity: {a['severity']}\n"
                    f"• Key symptoms: {a['symptoms'][:100]}...\n"
                    f"• Solution: {a['solution'][:80]}...\n\n"
                    f"**{b['name']}**\n"
                    f"• Severity: {b['severity']}\n"
                    f"• Key symptoms: {b['symptoms'][:100]}...\n"
                    f"• Solution: {b['solution'][:80]}...\n\n"
                    f"**More concerning:** {worse} is rated more severe."
                )
            return (
                "Please mention two disease names to compare. For example:\n"
                "• 'Compare tomato early blight and late blight'\n"
                "• 'What's the difference between corn rust and gray leaf spot?'"
            )

        # Weather advice
        if intent == 'weather_advice':
            text_lc = message.lower()
            if 'rain' in text_lc or 'wet' in text_lc or 'humid' in text_lc:
                return (
                    "**Wet/Humid Weather Advice:**\n\n"
                    "Rain and high humidity create perfect conditions for fungal diseases like:\n"
                    "• Late blight, early blight, and leaf mold\n\n"
                    "**Actions to take:**\n"
                    "• Increase field scouting frequency\n"
                    "• Ensure proper drainage to reduce standing water\n"
                    "• Apply preventive fungicides before extended wet periods\n"
                    "• Avoid working in wet fields to prevent spreading pathogens\n"
                    "• Increase plant spacing if possible to improve airflow\n\n"
                    "After rain, check lower leaves first — that's where moisture lingers longest."
                )
            elif 'dry' in text_lc or 'drought' in text_lc or 'hot' in text_lc:
                return (
                    "**Dry/Hot Weather Advice:**\n\n"
                    "Drought stress weakens plants and makes them more susceptible to:\n"
                    "• Spider mites (they thrive in dry, dusty conditions)\n"
                    "• Bacterial spot (stressed plants have reduced defenses)\n\n"
                    "**Actions to take:**\n"
                    "• Maintain consistent irrigation — stressed plants are vulnerable\n"
                    "• Water early morning to minimize evaporation\n"
                    "• Mulch around plants to retain soil moisture\n"
                    "• Watch for mite infestations (tiny dots, webbing, stippled leaves)\n\n"
                    "Healthy, well-hydrated plants resist disease much better."
                )
            else:
                return (
                    "Weather plays a huge role in disease outbreaks.\n\n"
                    "**General rule:**\n"
                    "• Wet/humid weather → fungal diseases (blights, molds, rusts)\n"
                    "• Hot/dry weather → mites and bacterial issues\n"
                    "• Cool/damp weather → many leaf spot diseases\n\n"
                    "Tell me what weather you're experiencing and I can give targeted advice!"
                )

        # Feedback help
        if intent == 'feedback_help':
            return (
                "**How to Report a Wrong Prediction:**\n\n"
                "1. Go to the Disease Detection section\n"
                "2. Scan a plant image\n"
                "3. After analysis, click 'Report Wrong Result'\n"
                "4. Enter the correct disease name\n\n"
                "**Why this matters:**\n"
                "Your feedback is stored and used to retrain the AI model daily. "
                "Every correction makes the system smarter and more accurate for everyone.\n\n"
                "You can also describe what you're seeing and I can help verify the diagnosis."
            )

        # General help fallback
        return (
            "I'm your **Smart Crop Assistant** with an open-source mind. Here's what I can do:\n\n"
            "**Disease Knowledge:**\n"
            "• Describe any disease in our database (symptoms, treatment, prevention)\n"
            "• Compare two diseases to understand differences\n"
            "• Check how severe a disease is\n\n"
            "**Your Data:**\n"
            "• Show your detection history and trends\n"
            "• Explain your most recent scan result\n"
            "• Analyze patterns across your farm\n\n"
            "**Diagnosis Help:**\n"
            "• Identify diseases from symptoms you describe\n"
            "• List diseases that affect specific crops\n"
            "• Give weather-based disease risk advice\n\n"
            "**Actions:**\n"
            "• Create treatment plans for detected diseases\n"
            "• Provide prevention strategies\n"
            "• Explain how to report wrong predictions\n\n"
            "What would you like to know? You can also just upload a plant image!"
        )

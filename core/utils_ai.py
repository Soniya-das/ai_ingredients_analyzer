# core/utils_ai.py

import logging
import json
import re
from google import genai
from django.conf import settings
from .models import Ingredient
from .utils import StaticIngredientAnalyzer

logger = logging.getLogger(__name__)


class RealAIAnalyzer:
    def __init__(self):
        self._client = None
        self._model_name = "gemini-2.5-flash"  # ✅ FIXED - changed from 2.0 to 2.5

    def _get_client(self):
        """Get or create Gemini client."""
        if self._client:
            return self._client
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            logger.warning("GEMINI_API_KEY not set – AI disabled.")
            return None
        try:
            self._client = genai.Client(api_key=api_key)
            return self._client
        except Exception as e:
            logger.error(f"Gemini init error: {e}", exc_info=True)
            return None

    def analyze_ingredients(self, ingredients_text, product_category='skincare'):
        """Analyze ingredients using Gemini AI."""
        client = self._get_client()
        if not client:
            logger.warning("AI client not available, falling back to static analysis")
            return StaticIngredientAnalyzer.analyze_ingredients(ingredients_text, product_category)

        prompt = f"""You are a professional ingredient safety analyst for cosmetics and personal care products.

PRODUCT CATEGORY: {product_category}

INGREDIENTS LIST:
{ingredients_text}

Analyze each ingredient scientifically and return ONLY valid JSON. Do not include any text outside the JSON.

Status meanings:
- "safe": Generally safe for most people at normal concentrations
- "moderate": May cause irritation or sensitivity in some individuals; use with caution
- "harmful": Known to cause adverse effects; should be avoided
- "unknown": Insufficient data available

Return format:
{{
  "ingredients": [
    {{
      "name": "exact ingredient name",
      "status": "safe|moderate|harmful|unknown",
      "reason": "scientific explanation for classification",
      "side_effects": "potential side effects (if any)"
    }}
  ],
  "safe_count": 0,
  "moderate_count": 0,
  "harmful_count": 0,
  "unknown_count": 0,
  "overall_status": "safe|moderate|harmful|unknown",
  "recommendation": "detailed recommendation for the user",
  "total_ingredients": 0
}}

Important: Return ONLY the JSON object. No markdown, no explanations, no additional text.
"""

        try:
            response = client.models.generate_content(
                model=self._model_name,
                contents=prompt
            )

            # Extract response text
            raw_text = response.text if hasattr(response, 'text') else str(response)
            
            logger.debug(f"AI Response: {raw_text[:500]}...")

            # Extract JSON safely
            json_text = self._extract_json(raw_text)
            
            if not json_text or json_text == "{}":
                raise ValueError("No valid JSON found in AI response")

            # Parse JSON
            result = json.loads(json_text)
            
            # Ensure all required fields exist
            result = self._normalize_result(result, ingredients_text, product_category)
            
            # Auto-save ingredients to database
            self._auto_save_ingredients(result.get("ingredients", []))
            
            return result

        except Exception as e:
            logger.error(f"AI analysis failed: {e}", exc_info=True)
            # Fallback to static analyzer
            return StaticIngredientAnalyzer.analyze_ingredients(ingredients_text, product_category)

    def _extract_json(self, text):
        """Extract JSON object from AI response."""
        if not text:
            return "{}"
        
        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Find JSON object
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return match.group(0)
        
        return "{}"

    def _normalize_result(self, result, ingredients_text, product_category):
        """Ensure result has all required fields and valid data."""
        if 'ingredients' not in result or not isinstance(result['ingredients'], list):
            result['ingredients'] = []
        
        for ing in result['ingredients']:
            ing['name'] = ing.get('name', '').strip()
            status = ing.get('status', 'unknown').lower()
            if status not in ('safe', 'moderate', 'harmful', 'unknown'):
                status = 'unknown'
            ing['status'] = status
            ing.setdefault('reason', 'No scientific data available')
            ing.setdefault('side_effects', 'Unknown')
        
        safe_cnt = sum(1 for i in result['ingredients'] if i.get('status') == 'safe')
        mod_cnt = sum(1 for i in result['ingredients'] if i.get('status') == 'moderate')
        harm_cnt = sum(1 for i in result['ingredients'] if i.get('status') == 'harmful')
        unknown_cnt = sum(1 for i in result['ingredients'] if i.get('status') == 'unknown')
        
        result['safe_count'] = result.get('safe_count', safe_cnt)
        result['moderate_count'] = result.get('moderate_count', mod_cnt)
        result['harmful_count'] = result.get('harmful_count', harm_cnt)
        result['unknown_count'] = result.get('unknown_count', unknown_cnt)
        result['total_ingredients'] = len(result['ingredients'])
        
        if 'overall_status' not in result or result['overall_status'] not in ('safe', 'moderate', 'harmful', 'unknown'):
            total = result['total_ingredients']
            if total > 0:
                if harm_cnt > 0:
                    overall = 'harmful'
                elif mod_cnt / total > 0.4:
                    overall = 'moderate'
                elif unknown_cnt / total > 0.7:
                    overall = 'moderate'
                else:
                    overall = 'safe'
                result['overall_status'] = overall
            else:
                result['overall_status'] = 'unknown'
        
        if not result.get('recommendation'):
            result['recommendation'] = self._generate_recommendation(
                result['overall_status'], 
                harm_cnt, mod_cnt, safe_cnt, unknown_cnt
            )
        
        return result

    def _generate_recommendation(self, overall, harmful, moderate, safe, unknown):
        """Generate a user-friendly recommendation."""
        if overall == 'harmful':
            return f"❌ NOT RECOMMENDED: Contains {harmful} harmful ingredient(s). Avoid this product completely."
        if harmful > 0:
            return f"⚠️ USE WITH CAUTION: Contains {harmful} harmful ingredient(s). Consider alternative products."
        if unknown > 0:
            return f"⚠️ {unknown} ingredient(s) could not be fully verified. AI analysis may not be 100% accurate. Patch test recommended."
        if overall == 'moderate':
            return f"⚖️ MODERATE RISK: Contains {moderate} moderate-risk ingredient(s). Suitable for non-sensitive users. Patch test before use."
        return f"✅ RECOMMENDED: All ingredients appear safe for regular use."

    def _auto_save_ingredients(self, ingredients):
        """Save AI-classified ingredients to database for future reference."""
        saved_count = 0
        for ing in ingredients:
            if not ing:
                continue
            
            name = ing.get("name", "").strip()
            if not name:
                continue
            
            status = ing.get("status", "unknown")
            reason = ing.get("reason", "")
            side_effects = ing.get("side_effects", "")
            
            if status in ('safe', 'moderate', 'harmful'):
                try:
                    obj, created = Ingredient.objects.get_or_create(
                        name=name,
                        defaults={
                            "category": status,
                            "description": reason[:500] if reason else f"{name} is classified as {status} by AI analysis.",
                            "side_effects": side_effects[:500] if side_effects else "",
                            "suitable_for": "General use (AI classified)",
                            "not_suitable_for": ""
                        }
                    )
                    if created:
                        saved_count += 1
                except Exception as e:
                    logger.error(f"Failed to save ingredient {name}: {e}")
        
        if saved_count > 0:
            logger.info(f"Saved {saved_count} new ingredients to database from AI analysis")

    @staticmethod
    def merge_static_and_ai(static_result, ai_result):
        """Merge static DB results with AI results, static has priority."""
        static_map = {}
        for ing in static_result.get('ingredients', []):
            name = ing.get('name', '').lower().strip()
            if name:
                static_map[name] = ing
        
        ai_map = {}
        for ing in ai_result.get('ingredients', []):
            name = ing.get('name', '').lower().strip()
            if name:
                ai_map[name] = ing
        
        merged_ingredients = []
        all_names = set(static_map.keys()) | set(ai_map.keys())
        
        for name in all_names:
            static_ing = static_map.get(name)
            ai_ing = ai_map.get(name)
            
            if static_ing and static_ing.get('status') != 'unknown':
                merged_ingredients.append(static_ing)
            elif ai_ing:
                merged_ingredients.append(ai_ing)
            elif static_ing:
                merged_ingredients.append(static_ing)
        
        safe_cnt = sum(1 for i in merged_ingredients if i.get('status') == 'safe')
        mod_cnt = sum(1 for i in merged_ingredients if i.get('status') == 'moderate')
        harm_cnt = sum(1 for i in merged_ingredients if i.get('status') == 'harmful')
        unknown_cnt = sum(1 for i in merged_ingredients if i.get('status') == 'unknown')
        total = len(merged_ingredients)
        
        if harm_cnt > 0:
            overall = 'harmful'
        elif mod_cnt / total > 0.4 if total > 0 else False:
            overall = 'moderate'
        elif unknown_cnt / total > 0.7 if total > 0 else False:
            overall = 'moderate'
        else:
            overall = 'safe'
        
        recommendation = StaticIngredientAnalyzer._get_recommendation(
            overall, harm_cnt, mod_cnt, safe_cnt, unknown_cnt, 'skincare'
        )
        
        return {
            'ingredients': merged_ingredients,
            'safe_count': safe_cnt,
            'moderate_count': mod_cnt,
            'harmful_count': harm_cnt,
            'unknown_count': unknown_cnt,
            'overall_status': overall,
            'recommendation': recommendation,
            'total_ingredients': total,
        }


# Global instance
ai_analyzer = RealAIAnalyzer()
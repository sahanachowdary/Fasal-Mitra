"""One Gemini request, no calls or SMS. Uses your project's Gemini quota."""
from demo_common import extract, recommend, AIError

if __name__ == '__main__':
    try:
        speech = input('Harvest details [Enter: I harvested 20 kg of rice]: ').strip()
        fields = extract(speech or 'I harvested 20 kg of rice')
        print('AI extracted:', fields)
        if fields.get('crop') not in (None, 'Other') and fields.get('kg'):
            print(recommend(fields))
        else:
            print('More details are needed. Nothing was invented.')
    except (AIError, ValueError) as exc:
        print('TEST NOT PASSED:', str(exc))

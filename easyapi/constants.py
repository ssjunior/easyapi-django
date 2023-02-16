#############################################################
# Custom-Attribute-Type
#############################################################

class CustomAttributeTypes():
    TEXT = 1
    NUMBER = 2
    DATE = 3
    OPTIONS = {
        TEXT: 'abc',
        NUMBER: '123',
        DATE: 'date',
    }
    OPTIONS_FLOW = {
        TEXT: 'text',
        NUMBER: 'number',
        DATE: 'date',
    }
    CHOICES = tuple(OPTIONS.items())


#############################################################
# Custom-Attribute-Presentations
#############################################################

class CustomAttributePresentations():
    TEXT = 1
    NUMBER = 2
    DATETIME = 3
    RADIO = 4
    CHECKBOX = 5
    DROPDOWN = 6
    TEXTAREA = 7
    DROPDOWN_COLOR = 8
    COLOR = 9
    VALUE = 10
    FIELDSET = 11
    OPTIONS = {
        TEXT: 'Text',
        NUMBER: 'Number',
        DATETIME: 'Datetime',
        RADIO: 'Radio Group',
        CHECKBOX: 'Checkbox',
        DROPDOWN: 'Dropdown',
        TEXTAREA: 'Textarea',
        DROPDOWN_COLOR: 'Dropdown Color',
        COLOR: 'Color',
        VALUE: 'Value',
    }
    CHOICES = tuple(OPTIONS.items())

from django import forms


class InviteGenerationForm(forms.Form):
    count = forms.IntegerField(label="生成数量", min_value=1, max_value=1000)
    validity_days = forms.TypedChoiceField(
        label="有效期",
        choices=((1, "1 天"), (3, "3 天"), (7, "7 天"), (30, "30 天")),
        coerce=int,
    )


class InviteRevocationForm(forms.Form):
    invite_ids = forms.MultipleChoiceField(label="选择邀请码")

    def __init__(self, *args, invite_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["invite_ids"].choices = invite_choices

-- EBA renumbers items every exercise (2420101 in 2024 is 2520101 in 2025).
-- item_key is the item's code in the latest exercise that has it, found by walking
-- the SDD's "code in the exercise before" links back from each latest code.
with recursive items as (
    select exercise, item, template, label, previous_exercise_item
    from {{ ref('stg_eba__items') }}
    where csv_file = 'tr_oth.csv'
),

chain as (
    -- items that no later exercise points back to: their own code is the key
    select
        i.exercise,
        i.item,
        i.item as item_key,
        i.template as item_template,
        i.label as item_label
    from items as i
    where not exists (
        select 1
        from items as later
        where later.exercise = i.exercise + 1
          and later.previous_exercise_item = i.item
    )

    union all

    select
        earlier.exercise,
        earlier.item,
        chain.item_key,
        chain.item_template,
        chain.item_label
    from chain
    inner join items as current_item
        on current_item.exercise = chain.exercise
       and current_item.item = chain.item
    inner join items as earlier
        on earlier.exercise = chain.exercise - 1
       and earlier.item = current_item.previous_exercise_item
)

select * from chain
